"""Shared, encrypted cache for broker OAuth access tokens.

Several modules across the codebase (the live broker adapter, the older
``FyersClient`` wrapper, and the standalone auth scripts under
``scripts/auth/``) each independently read/wrote ``.fyers_tokens.json`` as
plain JSON. That meant a live broker session token sat on disk — and in git
history — in plaintext. This module is the single place that does it, using
the same Fernet key already used for ``broker_credentials.json``
(:mod:`brokers.credentials`), so there is exactly one encrypted, atomically
written token cache per broker instead of six divergent copies.

Legacy plaintext caches are transparently migrated: the first read of an
old-format file re-encrypts it and rewrites the file before returning the
token.
"""

from __future__ import annotations

import json
import logging
import stat
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]  # trading-system/


def _cache_path(broker_id: str) -> Path:
    if broker_id == "fyers":
        # Preserve the existing on-disk filename for backward compatibility.
        return _ROOT / ".fyers_tokens.json"
    return _ROOT / f".{broker_id}_tokens.json"


def load_token(broker_id: str = "fyers") -> str:
    """Return the cached access token for ``broker_id``, or "" if none."""
    path = _cache_path(broker_id)
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read token cache %s: %s", path, exc)
        return ""

    enc_token = data.get("access_token_enc", "")
    if enc_token:
        from .credentials import decrypt_secret
        return decrypt_secret(enc_token)

    # Legacy plaintext cache — read once, then migrate to encrypted storage.
    legacy_token = data.get("access_token", "")
    if legacy_token:
        logger.warning(
            "%s: legacy plaintext token cache found — re-encrypting %s",
            broker_id, path,
        )
        save_token(legacy_token, broker_id)
    return legacy_token


def save_token(token: str, broker_id: str = "fyers") -> None:
    """Encrypt and atomically persist ``token`` for ``broker_id``."""
    from .credentials import encrypt_secret

    path = _cache_path(broker_id)
    payload = json.dumps({"access_token_enc": encrypt_secret(token)}, indent=2)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass
    logger.info("%s: access token cached (encrypted) → %s", broker_id, path)
