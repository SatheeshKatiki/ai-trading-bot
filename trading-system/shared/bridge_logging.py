"""Logging for api_bridge's uvicorn server: timestamped, and quiet about polling.

Two findings on 2026-10-15 in logs/api_bridge_stdout.log (373 MB):

* No line carried a time. uvicorn's default formats are ``LEVEL: message``,
  so the log could not be lined up with anything else -- e.g. the engine's
  WebSocket disconnects investigated that day.
* Of the ~70-100k lines a session now writes, nearly all are successful
  requests from the dashboard's polling (``/api/signals``, ``/api/quote``,
  ``/api/state``...), one line per poll, all session long.

The config below adds the time to every line and drops only successful GETs
of the polled endpoints. Every error status, every other request and every
WebSocket event is still logged.
"""
from __future__ import annotations

import copy
import logging

#: Endpoints the dashboard polls continuously.
POLLED_PATHS = frozenset({
    "/api/signals", "/api/quote", "/api/history", "/api/state",
    "/api/option-chain", "/api/logs", "/api/positions", "/health",
})

_DATEFMT = "%Y-%m-%d %H:%M:%S"


class QuietPollingFilter(logging.Filter):
    """Drop uvicorn access records for successful GETs of POLLED_PATHS."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not (isinstance(args, tuple) and len(args) == 5):
            return True
        _client, method, path_with_query, _version, status = args
        path = str(path_with_query).split("?", 1)[0]
        try:
            ok = int(status) < 400
        except (TypeError, ValueError):
            return True
        return not (method == "GET" and ok and path in POLLED_PATHS)


def uvicorn_log_config() -> dict:
    """uvicorn's own logging config, with timestamps and the polling filter."""
    import uvicorn.config

    cfg = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    formatters = cfg["formatters"]
    formatters["default"]["fmt"] = "%(asctime)s " + formatters["default"]["fmt"]
    formatters["access"]["fmt"] = "%(asctime)s " + formatters["access"]["fmt"]
    for formatter in formatters.values():
        formatter["datefmt"] = _DATEFMT
    cfg.setdefault("filters", {})["quiet_polling"] = {"()": QuietPollingFilter}
    cfg["handlers"]["access"]["filters"] = ["quiet_polling"]
    return cfg
