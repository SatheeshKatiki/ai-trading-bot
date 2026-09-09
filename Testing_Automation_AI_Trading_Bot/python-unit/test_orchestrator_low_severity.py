"""Two smaller orchestrator defects from the 2026-09-09 audit.

1. **pytz LMT.** ``datetime.combine(day, t, tzinfo=IST)`` attaches pytz's
   *first* historical offset for Asia/Kolkata -- LMT, ``+05:53`` -- not the
   modern ``+05:30``. The pre-market sleep was therefore computed 23 minutes
   short every time. Only ``IST.localize()`` selects the right offset.

2. **Port cleanup killed by substring.** The old implementation shelled out to
   ``netstat -aon | findstr :3000`` and fed the result to ``taskkill /F /T``.
   ``findstr`` is a plain substring match, so ``:3000`` also matched
   ``:30000``-``:30009`` and any *foreign* address ending in those digits --
   and ``/T`` kills the whole process tree. On a machine running anything in
   the 30000-32767 range (Docker, Kubernetes node ports, dev servers) this
   could take out unrelated software. The Linux branch had the same shape via
   ``fuser -k``.
"""

from __future__ import annotations

import ast
import datetime
import inspect
import io
import os
import tokenize

import pytz

import auto_daily_session as ads


IST = pytz.timezone("Asia/Kolkata")


def _code_only(src: str) -> str:
    """Strip comments and docstrings, leaving executable code.

    These tests assert that an old, dangerous construct is gone. The fixes
    deliberately *document* what they replaced, so a naive substring check
    matches the explanation rather than the code.
    """
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                continue
            out.append(tok)
        stripped = tokenize.untokenize(out)
    except Exception:
        stripped = "\n".join(
            line for line in src.splitlines() if not line.strip().startswith("#")
        )

    # Remove docstrings too.
    try:
        tree = ast.parse(stripped)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Module)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    stripped = stripped.replace(doc, "")
    except SyntaxError:
        pass
    return stripped


# ---------------------------------------------------------------------------
# pytz LMT
# ---------------------------------------------------------------------------

def test_tzinfo_form_really_does_produce_the_wrong_offset():
    """Pin the footgun itself, so nobody 'simplifies' the fix back."""
    naive = datetime.datetime.combine(datetime.date(2026, 9, 10), datetime.time(8, 45))
    wrong = naive.replace(tzinfo=IST)
    assert wrong.utcoffset() == datetime.timedelta(hours=5, minutes=53)


def test_localize_produces_the_correct_ist_offset():
    naive = datetime.datetime.combine(datetime.date(2026, 9, 10), datetime.time(8, 45))
    assert IST.localize(naive).utcoffset() == datetime.timedelta(hours=5, minutes=30)


def test_pre_market_sleep_is_no_longer_23_minutes_short():
    day = datetime.date(2026, 9, 10)
    now = IST.localize(datetime.datetime(2026, 9, 10, 8, 0))
    naive = datetime.datetime.combine(day, datetime.time(8, 45))

    wrong = (naive.replace(tzinfo=IST) - now).total_seconds()
    right = (IST.localize(naive) - now).total_seconds()

    assert right == 2700          # a real 45 minutes
    assert wrong == 1320          # what the old code computed
    assert right - wrong == 23 * 60


def test_daemon_loop_uses_localize_not_tzinfo():
    src = _code_only(inspect.getsource(ads.run_daemon_loop))
    assert "IST.localize(" in src
    assert "tzinfo=IST" not in src


def test_no_tzinfo_pytz_misuse_remains_in_the_module():
    src = _code_only(inspect.getsource(ads))
    assert "tzinfo=IST" not in src


# ---------------------------------------------------------------------------
# Port cleanup
# ---------------------------------------------------------------------------

def test_port_cleanup_no_longer_shells_out_to_findstr():
    src = _code_only(inspect.getsource(ads.kill_process_on_ports))
    assert "findstr" not in src, "substring port matching is back"
    assert "taskkill" not in src
    assert "fuser" not in src


def test_port_cleanup_matches_the_port_exactly():
    src = _code_only(inspect.getsource(ads.kill_process_on_ports))
    assert "psutil" in src
    assert "CONN_LISTEN" in src
    assert "laddr.port not in wanted" in src or "laddr.port" in src


def test_port_cleanup_is_a_no_op_on_a_free_port():
    """Must not raise, and must not touch anything, when nothing is listening."""
    ads.kill_process_on_ports([65_432])


def test_port_cleanup_never_kills_itself_or_its_parent(monkeypatch):
    """The orchestrator owns port 8000's child; it must not kill its own tree."""
    killed = []

    class _FakeAddr:
        def __init__(self, port):
            self.port = port

    class _FakeConn:
        def __init__(self, pid, port):
            self.pid, self.laddr = pid, _FakeAddr(port)
            self.status = "LISTEN"

    import psutil

    self_pid, parent_pid = os.getpid(), os.getppid()
    monkeypatch.setattr(psutil, "CONN_LISTEN", "LISTEN", raising=False)
    monkeypatch.setattr(
        psutil, "net_connections",
        lambda kind="inet": [_FakeConn(self_pid, 8000), _FakeConn(parent_pid, 8000)],
    )

    class _Boom:
        def __init__(self, pid):
            killed.append(pid)

    monkeypatch.setattr(psutil, "Process", _Boom)

    ads.kill_process_on_ports([8000])

    assert killed == [], "must never kill its own process or its parent"


def test_port_cleanup_survives_access_denied(monkeypatch):
    """Enumerating sockets needs privileges on some hosts; that is not fatal."""
    import psutil

    def _denied(kind="inet"):
        raise psutil.AccessDenied()

    monkeypatch.setattr(psutil, "net_connections", _denied)
    ads.kill_process_on_ports([8000])   # must not raise
