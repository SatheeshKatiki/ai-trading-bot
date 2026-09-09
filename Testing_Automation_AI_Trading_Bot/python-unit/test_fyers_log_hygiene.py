"""Regression tests for bounding the Fyers SDK's own log files (2026-09-09).

The vendored ``fyers_apiv3`` SDK hardcodes plain, non-rotating handlers in
``FyersModel.__init__``::

    logger_handler=logging.FileHandler(self.log_path + "fyersApi.log")
    logger_handler=logging.FileHandler(self.log_path + "fyersRequests.log")

`api_bridge.py` did install a RotatingFileHandler for ``fyersApi.log``, but on
the ROOT logger -- the SDK writes through its own *named* logger straight into
the same path, so the rotation was cosmetic. Observed on disk during the audit:

    fyersApi.log        37 MB   (despite a 5 MB x 3 policy)
    fyersRequests.log   52 MB   (no rotation configured anywhere)
    fyersApi.log.3     8.9 MB
    ------------------------------------------------------------
    total             129 MB    and growing without bound

Two facts established empirically before choosing the fix, both worth pinning:

* Pre-registering a RotatingFileHandler on the SDK's logger names does **not**
  win -- the SDK appends its own plain FileHandler alongside it.
* A rotating handler installed *after* construction **does** survive every
  later ``FyersModel`` build, and the SDK does not accumulate duplicates.

So taming must run after construction, and doing so once is durable.
"""

from __future__ import annotations

import logging
import logging.handlers

import pytest

from shared.fyers_log_hygiene import (
    DEFAULT_BACKUP_COUNT,
    DEFAULT_MAX_BYTES,
    tame_fyers_sdk_logging,
)


SDK_LOGGERS = ("FyersAPI", "FyersAPIRequest")


@pytest.fixture
def sdk_loggers(tmp_path):
    """Give each SDK logger a plain FileHandler, as the SDK itself would."""
    saved = {name: list(logging.getLogger(name).handlers) for name in SDK_LOGGERS}
    for name in SDK_LOGGERS:
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.addHandler(logging.FileHandler(tmp_path / f"{name}.log", delay=True))
    yield tmp_path
    for name, handlers in saved.items():
        logging.getLogger(name).handlers = handlers


def _file_handlers(name):
    return [h for h in logging.getLogger(name).handlers
            if isinstance(h, logging.FileHandler)]


@pytest.mark.parametrize("name", SDK_LOGGERS)
def test_plain_file_handler_is_replaced_with_a_rotating_one(sdk_loggers, name):
    assert type(_file_handlers(name)[0]) is logging.FileHandler

    tame_fyers_sdk_logging()

    handlers = _file_handlers(name)
    assert len(handlers) == 1, "must swap, not accumulate"
    assert isinstance(handlers[0], logging.handlers.RotatingFileHandler)


def test_rotation_limits_are_applied(sdk_loggers):
    tame_fyers_sdk_logging()
    for name in SDK_LOGGERS:
        h = _file_handlers(name)[0]
        assert h.maxBytes == DEFAULT_MAX_BYTES
        assert h.backupCount == DEFAULT_BACKUP_COUNT


def test_total_footprint_is_bounded(sdk_loggers):
    """The whole point: a hard ceiling instead of unbounded growth.

    2 files x (1 active + 3 backups) x 5 MB = 40 MB, versus 129 MB observed.
    """
    tame_fyers_sdk_logging()
    worst_case = sum(
        h.maxBytes * (h.backupCount + 1)
        for name in SDK_LOGGERS for h in _file_handlers(name)
    )
    assert worst_case <= 64 * 1024 * 1024
    assert worst_case == 2 * DEFAULT_MAX_BYTES * (DEFAULT_BACKUP_COUNT + 1)


def test_the_log_path_is_preserved(sdk_loggers):
    """Rotation must not silently relocate the file it rotates."""
    before = {name: _file_handlers(name)[0].baseFilename for name in SDK_LOGGERS}
    tame_fyers_sdk_logging()
    after = {name: _file_handlers(name)[0].baseFilename for name in SDK_LOGGERS}
    assert before == after


def test_is_idempotent(sdk_loggers):
    """Safe to call after every FyersModel construction."""
    tame_fyers_sdk_logging()
    first = {name: _file_handlers(name)[0] for name in SDK_LOGGERS}

    for _ in range(5):
        tame_fyers_sdk_logging()

    for name in SDK_LOGGERS:
        handlers = _file_handlers(name)
        assert len(handlers) == 1
        assert handlers[0] is first[name], "an already-rotating handler must be left alone"


def test_request_logger_level_is_raised_off_debug(sdk_loggers):
    """The SDK pins FyersAPIRequest to DEBUG, logging every request/response.

    That is the single biggest contributor to the 52 MB file.
    """
    logging.getLogger("FyersAPIRequest").setLevel(logging.DEBUG)
    tame_fyers_sdk_logging()
    assert logging.getLogger("FyersAPIRequest").level == logging.INFO


def test_request_log_level_is_overridable(sdk_loggers, monkeypatch):
    """Debugging a broker issue must not require editing vendored code."""
    monkeypatch.setenv("FYERS_REQUEST_LOG_LEVEL", "DEBUG")
    tame_fyers_sdk_logging()
    assert logging.getLogger("FyersAPIRequest").level == logging.DEBUG


def test_never_raises_on_a_hostile_logger(monkeypatch):
    """Logging hygiene must not be able to take down a trading process."""
    class Exploding(logging.Handler):
        @property
        def baseFilename(self):
            raise RuntimeError("boom")

    lg = logging.getLogger("FyersAPI")
    saved = list(lg.handlers)
    lg.handlers = [Exploding()]
    try:
        tame_fyers_sdk_logging()   # must not raise
    finally:
        lg.handlers = saved


def test_unknown_logger_names_are_a_no_op():
    assert tame_fyers_sdk_logging(logger_names=["NoSuchLoggerXYZ"]) == []
