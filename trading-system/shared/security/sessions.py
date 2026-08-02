"""Server-verified session store for the dashboard API.

Root cause this fixes
----------------------
Before this module existed, ``/api/auth/login`` and ``/api/auth/register``
returned a predictable, unsigned string like ``f"mana_ai_auth_{user_id}_valid"``
as the "token". Nothing on the server ever recorded or re-validated that
string — any caller could fabricate one for any user id and it would be
accepted as proof of identity by the frontend (which only checked that
*some* truthy value existed in ``localStorage``). There was no way for
``api_bridge.py`` to authenticate a request even if it wanted to.

This module is the missing piece: real, unguessable, server-tracked
sessions that both the frontend and the API bridge can rely on as the
actual source of truth for "is this request authenticated".

Sessions are persisted to ``config/sessions.json`` (atomic writes, same
pattern as ``config/users.json``) so a backend restart does not silently
log every operator out.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]  # trading-system/
_SESSIONS_FILE = _ROOT / "config" / "sessions.json"

DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


def _load() -> dict:
    if not _SESSIONS_FILE.exists():
        return {}
    try:
        with open(_SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("Failed to load sessions.json: %s", exc)
        return {}


def _save(sessions: dict) -> None:
    try:
        _SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=_SESSIONS_FILE.parent, prefix="sessions_tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(sessions, f, indent=2)
            os.replace(tmp_path, _SESSIONS_FILE)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    except Exception as exc:
        logger.error("Failed to save sessions.json: %s", exc)


def _purge_expired(sessions: dict) -> dict:
    now = time.time()
    return {tok: s for tok, s in sessions.items() if s.get("expires_at", 0) > now}


def create_session(user_id: str, name: str = "", email: str = "",
                    ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Create a new unguessable session token for ``user_id`` and persist it."""
    token = secrets.token_urlsafe(32)
    sessions = _purge_expired(_load())
    now = time.time()
    sessions[token] = {
        "user_id": user_id,
        "name": name,
        "email": email,
        "created_at": now,
        "expires_at": now + ttl_seconds,
    }
    _save(sessions)
    return token


def validate_session(token: Optional[str]) -> Optional[dict]:
    """Return the session record for ``token`` if it exists and hasn't expired."""
    if not token:
        return None
    sessions = _load()
    record = sessions.get(token)
    if not record:
        return None
    if record.get("expires_at", 0) <= time.time():
        # Lazily purge on access rather than on every request.
        sessions.pop(token, None)
        _save(sessions)
        return None
    return record


def revoke_session(token: Optional[str]) -> None:
    """Invalidate a single session token (logout)."""
    if not token:
        return
    sessions = _load()
    if sessions.pop(token, None) is not None:
        _save(sessions)


def revoke_all_sessions_for_user(user_id: str) -> None:
    """Invalidate every session belonging to ``user_id`` (e.g. on password reset)."""
    sessions = _load()
    remaining = {tok: s for tok, s in sessions.items() if s.get("user_id") != user_id}
    if len(remaining) != len(sessions):
        _save(remaining)
