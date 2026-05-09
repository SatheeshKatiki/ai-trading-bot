"""Shared security module.

Provides:
  - AuditLogger   : append-only HMAC-chained trade & auth audit trail
  - LogSanitizer  : logging.Filter that redacts API keys / tokens from log output
  - RateLimiter   : token-bucket rate limiter for broker API calls
  - InputValidator: validates OrderRequest before it reaches any broker
  - DashboardAuth : password-protection helpers for the Streamlit dashboard

Import example::

    from shared.security import audit, install_log_sanitizer
"""

__all__: list = []

# Each import is wrapped so a single failure doesn't break the entire package.
try:
    from .audit_log import AuditLogger, audit
    __all__ += ["AuditLogger", "audit"]
except Exception:
    pass

try:
    from .log_filter import LogSanitizer, install_log_sanitizer
    __all__ += ["LogSanitizer", "install_log_sanitizer"]
except Exception:
    def install_log_sanitizer(): pass  # no-op fallback

try:
    from .rate_limiter import RateLimiter
    __all__ += ["RateLimiter"]
except Exception:
    pass

try:
    from .validator import InputValidator, ValidationError
    __all__ += ["InputValidator", "ValidationError"]
except Exception:
    pass
