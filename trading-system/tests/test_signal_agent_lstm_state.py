"""Regression tests for SignalAgent's LSTM state persistence
(drl/marl/signal_agent.py's save_state/load_state).

Root-cause fix (Low audit finding): these previously used pickle.dump/
pickle.load to persist lstm_states -- an insecure-deserialization
pattern (CWE-502): if something with local write access ever
substituted a crafted file at that path, pickle.load can execute
arbitrary code on the next restart. lstm_states is always a 2-tuple of
plain numpy arrays (confirmed against sb3_contrib's
RecurrentActorCriticPolicy.predict(), which returns
`(states[0].cpu().numpy(), states[1].cpu().numpy())`), so there's no
need for pickle's ability to serialize arbitrary objects -- switched to
numpy's native .npz format with `allow_pickle=False`, which can only
ever produce plain arrays on load.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from drl.marl.signal_agent import SignalAgent

# Module-level (not a local closure variable) so that pickling a reference
# to _mark_pwned survives a real pickle dump/load round-trip: pickle
# serializes plain top-level functions by (module, qualname) reference and
# re-resolves that same real function object on load, whereas a bound
# method of a local object would reconstruct a *copy* of that object and
# silently mutate the copy instead of anything the test can observe.
_pwned_marker: list = []


def _mark_pwned():
    _pwned_marker.append(True)


def _inactive_agent() -> SignalAgent:
    """SignalAgent with no real model -- gracefully becomes inactive
    (is_active=False), but save_state/load_state operate purely on
    self.lstm_states and don't depend on is_active."""
    return SignalAgent(model_path="__no_such_model__.zip")


def test_save_state_writes_npz_not_pickle(tmp_path):
    agent = _inactive_agent()
    agent.lstm_states = (np.ones((1, 4)), np.zeros((1, 4)))
    filepath = str(tmp_path / "lstm_memory.npz")

    agent.save_state(filepath)

    # np.load with allow_pickle=False succeeding at all proves the file
    # is a genuine numpy archive, not a pickle stream (which would fail
    # numpy's zip/magic-number parsing).
    with np.load(filepath, allow_pickle=False) as payload:
        assert set(payload.files) >= {"h", "c", "saved_date_ist"}
        np.testing.assert_array_equal(payload["h"], np.ones((1, 4)))
        np.testing.assert_array_equal(payload["c"], np.zeros((1, 4)))


def test_load_state_same_day_round_trip(tmp_path):
    agent = _inactive_agent()
    agent.lstm_states = (np.array([[1.0, 2.0]]), np.array([[3.0, 4.0]]))
    agent.episode_starts = np.array([True])
    filepath = str(tmp_path / "lstm_memory.npz")
    agent.save_state(filepath)

    fresh = _inactive_agent()
    fresh.load_state(filepath)

    np.testing.assert_array_equal(fresh.lstm_states[0], [[1.0, 2.0]])
    np.testing.assert_array_equal(fresh.lstm_states[1], [[3.0, 4.0]])
    assert fresh.episode_starts[0] == False  # noqa: E712 -- genuine same-day continuation


def test_load_state_discards_stale_different_day(tmp_path, monkeypatch):
    agent = _inactive_agent()
    agent.lstm_states = (np.ones((1, 2)), np.ones((1, 2)))
    filepath = str(tmp_path / "lstm_memory.npz")
    agent.save_state(filepath)

    # Make "today" (IST) appear to be a different date than what was saved.
    import drl.marl.signal_agent as sig_mod
    from datetime import datetime, timedelta

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2099, 1, 1, tzinfo=tz)

    monkeypatch.setattr(sig_mod, "datetime", _FakeDatetime)

    fresh = _inactive_agent()
    fresh.load_state(filepath)

    assert fresh.lstm_states is None
    assert fresh.episode_starts[0] == True  # noqa: E712 -- fresh episode, not continued


def test_load_state_rejects_raw_pickle_stream(tmp_path):
    """A leftover legacy .pkl-style pickle file at the new default path
    isn't even valid npz format, so np.load() rejects it during format
    detection regardless of allow_pickle -- confirms load_state() falls
    back to a fresh episode instead of crashing."""
    import pickle

    filepath = str(tmp_path / "lstm_memory.npz")
    with open(filepath, "wb") as f:
        pickle.dump({"lstm_states": (np.ones((1, 2)), np.ones((1, 2))), "saved_date_ist": "2020-01-01"}, f)

    agent = _inactive_agent()
    agent.load_state(filepath)  # must not raise, must not restore state

    assert agent.lstm_states is None


def test_load_state_does_not_unpickle_object_arrays():
    """The actual thing allow_pickle=False protects against: a
    well-formed .npz can still smuggle a malicious payload via an
    object-dtype array whose __reduce__ executes code when unpickled.
    np.load(..., allow_pickle=False) (what load_state() uses) must
    refuse to deserialize it -- np.load(..., allow_pickle=True) would
    happily run it. This proves allow_pickle=False is load-bearing, not
    just an unused hardening flag."""
    _pwned_marker.clear()
    class _Payload:
        def __reduce__(self):
            return (_mark_pwned, ())

    import io
    buf = io.BytesIO()
    np.savez(buf, evil=np.array(_Payload(), dtype=object))
    buf.seek(0)

    # allow_pickle=False (what load_state() actually uses) must refuse.
    with pytest.raises(ValueError):
        with np.load(buf, allow_pickle=False) as payload:
            _ = payload["evil"]
    assert _pwned_marker == []

    # Sanity check that this isn't a vacuous test: allow_pickle=True
    # WOULD execute the payload, proving the object array is genuinely
    # malicious and the False setting is what's stopping it.
    buf.seek(0)
    with np.load(buf, allow_pickle=True) as payload:
        _ = payload["evil"]
    assert _pwned_marker == [True]


def test_load_state_end_to_end_does_not_execute_malicious_h_array(tmp_path):
    """End-to-end version of the allow_pickle proof above, but going
    through SignalAgent.load_state() itself (not numpy directly) --
    catches a regression if load_state()'s own np.load call is ever
    changed back to allow_pickle=True."""
    _pwned_marker.clear()
    class _Payload:
        def __reduce__(self):
            return (_mark_pwned, ())

    import io
    from datetime import datetime
    filepath = str(tmp_path / "lstm_memory.npz")
    buf = io.BytesIO()
    np.savez(
        buf,
        h=np.array(_Payload(), dtype=object),
        c=np.ones((1, 2)),
        saved_date_ist=np.array(datetime.now(_IST_for_test()).strftime("%Y-%m-%d")),
    )
    Path(filepath).write_bytes(buf.getvalue())

    agent = _inactive_agent()
    agent.load_state(filepath)  # must not execute the payload

    assert _pwned_marker == []


def _IST_for_test():
    from datetime import timezone, timedelta
    return timezone(timedelta(hours=5, minutes=30))


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_save_state_writes_npz_not_pickle(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_load_state_same_day_round_trip(Path(d))
    print("All SignalAgent LSTM-state tests passed (run via pytest for full coverage).")
