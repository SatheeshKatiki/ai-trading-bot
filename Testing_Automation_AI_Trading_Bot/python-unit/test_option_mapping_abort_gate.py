"""Regression coverage for the 2026-08-07 audit's "no abort on
select_option() failure" finding (docs/STRATEGY_AUDIT_2026-08-07.md §1.1).

Root cause: `entry_symbol` defaulted to the raw underlying index symbol
before `select_option()` was attempted, and was only overwritten on
success. The auto-map call was wrapped in a bare `try/except Exception`
with no abort -- if `select_option()` ever raised, execution fell through
into the rest of the entry pipeline with `entry_symbol` still equal to the
index symbol, which every downstream check (`is_option_trade`,
`resolve_initial_stop`, order placement) would then treat as if it were an
option premium -- a direct violation of the option-buying-only mandate.

Fixed by tracking `option_mapping_required`/`option_mapping_succeeded`
explicitly and aborting the tick via `_should_abort_missing_option_mapping()`
if mapping was required but didn't succeed. This test pins that pure
decision function against every relevant combination.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.main import _should_abort_missing_option_mapping


def test_aborts_when_mapping_required_but_failed():
    assert _should_abort_missing_option_mapping("ema_rsi", True, False) is True


def test_does_not_abort_when_mapping_required_and_succeeded():
    assert _should_abort_missing_option_mapping("ema_rsi", True, True) is False


def test_does_not_abort_when_mapping_was_never_required():
    """A non-index symbol (or a zero signal) never attempts the auto-map at
    all -- nothing to abort for."""
    assert _should_abort_missing_option_mapping("ema_rsi", False, False) is False


def test_premium_strategy_is_never_aborted_by_this_gate():
    """"premium" builds entry_symbol via its own PremiumSignalEngine path,
    already gated by sig.is_tradeable before this check is ever reached --
    it must never be blocked by this specific gate, even in the
    (impossible in practice) case both flags are set."""
    assert _should_abort_missing_option_mapping("premium", True, False) is False
    assert _should_abort_missing_option_mapping("premium", False, False) is False


def test_institutional_momentum_is_covered_by_this_gate_like_any_other_registry_strategy():
    assert _should_abort_missing_option_mapping("institutional_momentum", True, False) is True
    assert _should_abort_missing_option_mapping("institutional_momentum", True, True) is False
