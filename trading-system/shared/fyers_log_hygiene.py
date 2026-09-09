"""Bound the Fyers SDK's own log files.

The vendored ``fyers_apiv3`` SDK builds its two loggers with a plain,
non-rotating handler, hardcoded in ``fyersModel.FyersModel.__init__``::

    self.api_logger = FyersLogger(
        "FyersAPI", log_level, stack_level=2,
        logger_handler=logging.FileHandler(self.log_path + "fyersApi.log"))

    self.request_logger = FyersLogger(
        "FyersAPIRequest", "DEBUG", stack_level=2,
        logger_handler=logging.FileHandler(self.log_path + "fyersRequests.log"))

Two consequences, both observed in this repository on 2026-09-09:

* ``api_bridge.py`` installs a ``RotatingFileHandler`` for ``fyersApi.log``
  (5 MB x 3) on the ROOT logger, but the SDK writes through its own named
  logger straight into the same path with an unbounded handler. The rotation
  was therefore cosmetic: the file stood at **37 MB**.
* ``fyersRequests.log`` has no rotation configured anywhere at all, is pinned
  at ``DEBUG`` by the SDK regardless of the caller's log level, and logs every
  request and response. It stood at **52 MB**. Total on-disk log footprint was
  **129 MB** and growing without bound.

This module swaps those handlers for size-bounded ones. It is deliberately
defensive: it never raises, and it is idempotent, so it can be called after
every ``FyersModel`` construction as well as once at start-up.

Nothing here patches the vendored package -- an upgrade would silently revert
that. It reconfigures the loggers the SDK has already created, by name.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

#: The named loggers the SDK creates, and the file each writes to.
_SDK_LOGGERS = {
    "FyersAPI": "fyersApi.log",
    "FyersAPIRequest": "fyersRequests.log",
}

#: 5 MB x 3 backups per file, matching api_bridge.py's own rotation policy.
#: Worst case on disk: 2 files x 4 x 5 MB = 40 MB, versus the 129 MB observed.
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3

#: The SDK hardcodes the request logger to DEBUG, which is what makes
#: fyersRequests.log grow fastest. Overridable for debugging a broker issue.
_REQUEST_LOG_LEVEL_ENV = "FYERS_REQUEST_LOG_LEVEL"


def _is_plain_file_handler(handler: logging.Handler) -> bool:
    """A FileHandler that is NOT already one of the rotating subclasses."""
    return (
        isinstance(handler, logging.FileHandler)
        and not isinstance(handler, logging.handlers.RotatingFileHandler)
        and not isinstance(handler, logging.handlers.TimedRotatingFileHandler)
    )


def tame_fyers_sdk_logging(
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    logger_names: Iterable[str] | None = None,
) -> list[str]:
    """Replace the SDK's unbounded file handlers with rotating ones.

    Returns the list of file paths that were re-bounded, so a caller can log
    what it changed. Never raises: logging hygiene must not be able to take
    down a trading process.
    """
    swapped: list[str] = []

    for name in (logger_names or _SDK_LOGGERS):
        try:
            sdk_logger = logging.getLogger(name)

            for handler in list(sdk_logger.handlers):
                if not _is_plain_file_handler(handler):
                    continue

                path = Path(getattr(handler, "baseFilename", "") or "")
                if not path.name:
                    continue

                rotating = logging.handlers.RotatingFileHandler(
                    str(path),
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                    delay=True,
                )
                rotating.setLevel(handler.level)
                if handler.formatter is not None:
                    rotating.setFormatter(handler.formatter)

                sdk_logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass
                sdk_logger.addHandler(rotating)
                swapped.append(str(path))

            # The SDK pins the request logger to DEBUG, which is the single
            # biggest contributor to log growth. Allow raising it without
            # touching the vendored package.
            if name == "FyersAPIRequest":
                level = os.environ.get(_REQUEST_LOG_LEVEL_ENV, "INFO").upper()
                if level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
                    sdk_logger.setLevel(getattr(logging, level))
        except Exception as exc:      # pragma: no cover - defensive only
            logger.debug("Could not tame SDK logger %s: %s", name, exc)

    if swapped:
        logger.info(
            "Bounded Fyers SDK log files (%d MB x %d each): %s",
            max_bytes // (1024 * 1024), backup_count + 1, ", ".join(swapped),
        )
    return swapped
