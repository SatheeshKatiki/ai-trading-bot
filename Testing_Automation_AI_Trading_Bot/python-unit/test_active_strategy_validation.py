"""Regression coverage for the 2026-08-07 audit's "no active_strategy
validation" finding (docs/STRATEGY_AUDIT_2026-08-07.md §4.7).

Root cause: `registry.run_strategy()` raises `ValueError` for an
unregistered strategy name, but that's caught by a broad
`try/except Exception` deep in main.py's tick-processing loop and just
logged -- a typo in `active_strategy`, or a strategy that failed to
auto-register due to an import error, would make the engine raise and
retry on every single tick, forever, while still reporting healthy at the
process/health-check level and generating zero real trade signals.

Fixed with `_validate_active_strategy()`, called once per actual settings
(re)load (not per-tick) from inside `_load_settings()`, logging a CRITICAL
line the first time a bad value is seen and staying quiet on repeats of
the same bad value (so a persistently-misconfigured setting doesn't spam
the log once per file-mtime-change either).
"""
import logging

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import trading_bot.main as main_module


def test_registered_strategy_name_does_not_warn(caplog):
    main_module._last_bad_active_strategy = None
    with caplog.at_level(logging.CRITICAL, logger="trading_bot.main"):
        main_module._validate_active_strategy("ema_rsi")
    assert not any(r.levelno >= logging.CRITICAL for r in caplog.records)


def test_premium_is_valid_via_the_outside_registry_allowlist(caplog):
    """"premium" is handled by a dedicated main.py branch and never goes
    through registry.run_strategy() for entries -- explicitly allow-listed
    so it stays valid even on a build where it happens not to also be
    separately auto-registered."""
    main_module._last_bad_active_strategy = None
    assert "premium" in main_module._STRATEGIES_OUTSIDE_REGISTRY
    with caplog.at_level(logging.CRITICAL, logger="trading_bot.main"):
        main_module._validate_active_strategy("premium")
    assert not any(r.levelno >= logging.CRITICAL for r in caplog.records)


def test_institutional_momentum_is_registered_and_valid(caplog):
    """Confirms the momentum_strategy package's STRATEGY_NAME actually
    matches what main.py's default active_strategy expects -- if this
    ever silently drifted apart, this test would catch it."""
    main_module._last_bad_active_strategy = None
    assert "institutional_momentum" in main_module.registry.registered_strategies
    with caplog.at_level(logging.CRITICAL, logger="trading_bot.main"):
        main_module._validate_active_strategy("institutional_momentum")
    assert not any(r.levelno >= logging.CRITICAL for r in caplog.records)


def test_unregistered_strategy_name_logs_critical_once(caplog):
    main_module._last_bad_active_strategy = None
    bad_name = "ema__rsi_typo_does_not_exist"
    assert bad_name not in main_module.registry.registered_strategies

    with caplog.at_level(logging.CRITICAL, logger="trading_bot.main"):
        main_module._validate_active_strategy(bad_name)
        main_module._validate_active_strategy(bad_name)
        main_module._validate_active_strategy(bad_name)

    critical_records = [r for r in caplog.records if r.levelno >= logging.CRITICAL]
    assert len(critical_records) == 1
    assert bad_name in critical_records[0].getMessage()


def test_recovering_to_a_valid_name_clears_the_warned_state(caplog):
    """After a bad value is corrected, re-introducing the SAME bad value
    later should warn again -- not stay silenced forever."""
    main_module._last_bad_active_strategy = None
    bad_name = "another_typo_xyz"

    with caplog.at_level(logging.CRITICAL, logger="trading_bot.main"):
        main_module._validate_active_strategy(bad_name)
        main_module._validate_active_strategy("ema_rsi")  # operator fixes it
        main_module._validate_active_strategy(bad_name)   # then breaks it again

    critical_records = [r for r in caplog.records if r.levelno >= logging.CRITICAL]
    assert len(critical_records) == 2


def test_none_or_empty_strategy_name_does_not_crash(caplog):
    main_module._last_bad_active_strategy = None
    with caplog.at_level(logging.CRITICAL, logger="trading_bot.main"):
        main_module._validate_active_strategy(None)
        main_module._validate_active_strategy("")
    assert not any(r.levelno >= logging.CRITICAL for r in caplog.records)
