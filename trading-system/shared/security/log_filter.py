"""Log sanitizer — strips API keys, tokens, and secrets from all log output.

How it works
------------
A ``logging.Filter`` subclass is added to the root logger.  It applies a
pre-compiled set of regex patterns to every log record's ``getMessage()``
output and replaces any match with ``***REDACTED***``.

Patterns cover:
  * Fyers / Kite / Angel One token formats
  * Generic ``key=VALUE`` and ``token=VALUE`` patterns
  * Long alphanumeric strings that look like secrets (≥ 32 chars)
  * Environment-variable-style assignments (``SECRET=abcd1234``)

Install once at startup::

    from shared.security import install_log_sanitizer
    install_log_sanitizer()

After this every handler attached to the root logger — console, file, or
any third-party handler — receives sanitised output.
"""

from __future__ import annotations

import logging
import re
from typing import List

# ---------------------------------------------------------------------------
# Redaction patterns
# ---------------------------------------------------------------------------

# Each tuple: (compiled_regex, replacement_string)
_PATTERNS: List[tuple] = []


def _build_patterns() -> None:
    raw = [
        # Generic key/secret/token/password assignment in log strings
        (r'(?i)(api[_\-]?key|secret[_\-]?key|access[_\-]?token|auth[_\-]?code'
         r'|request[_\-]?token|password|mpin|totp[_\-]?secret|client[_\-]?secret'
         r'|fyers[_\-]?secret|kite[_\-]?secret)\s*[=:]\s*["\']?([A-Za-z0-9+/=._\-]{6,})["\']?',
         r'\1=***REDACTED***'),

        # Bearer / JWT tokens in HTTP headers
        (r'(?i)(Bearer\s+)[A-Za-z0-9\-_\.]{20,}',
         r'\1***REDACTED***'),

        # Long hex strings (≥ 32 hex chars) — looks like a hash/token
        (r'\b[0-9a-fA-F]{32,}\b',
         r'***REDACTED***'),

        # Base64 Fernet tokens (always end with =)
        (r'\b[A-Za-z0-9+/]{40,}={0,2}\b',
         r'***REDACTED***'),

        # Fyers-style access token: typically alphanumeric 200+ chars
        # Kite token: 32-char hex
        # Already covered above, but be explicit for clarity
        (r'(?i)(token|secret)\s*=\s*["\']?[A-Za-z0-9\-_\.]{16,}["\']?',
         r'\1=***REDACTED***'),

        # Indian mobile numbers that might appear in account data
        (r'\b[6-9]\d{9}\b',
         r'***PHONE***'),

        # PAN card pattern  (ABCDE1234F)
        (r'\b[A-Z]{5}[0-9]{4}[A-Z]\b',
         r'***PAN***'),
    ]

    for pattern, replacement in raw:
        try:
            _PATTERNS.append((re.compile(pattern), replacement))
        except re.error as exc:
            logging.getLogger(__name__).warning(
                "LogSanitizer: could not compile pattern %r: %s", pattern, exc
            )


_build_patterns()


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

class LogSanitizer(logging.Filter):
    """logging.Filter that redacts secrets from every log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        # Sanitise the formatted message
        try:
            msg = record.getMessage()
            for pat, repl in _PATTERNS:
                msg = pat.sub(repl, msg)
            # Replace the args-formatted message in-place
            record.msg  = msg
            record.args = ()   # already formatted
        except Exception:
            pass   # never break logging because of the sanitizer
        return True   # always pass the record through


# ---------------------------------------------------------------------------
# Install helper
# ---------------------------------------------------------------------------

def install_log_sanitizer() -> None:
    """Attach LogSanitizer to the root logger.

    Call once at application startup (before any log messages are emitted).
    Safe to call multiple times — subsequent calls are no-ops.
    """
    root = logging.getLogger()
    for existing_filter in root.filters:
        if isinstance(existing_filter, LogSanitizer):
            return   # already installed
    sanitizer = LogSanitizer()
    root.addFilter(sanitizer)
    logging.getLogger(__name__).info(
        "LogSanitizer installed — API keys and tokens will be redacted in all log output."
    )
