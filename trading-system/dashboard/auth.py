"""Dashboard password authentication for Streamlit.

Provides a lightweight, dependency-free session-based password gate.
No external auth library required — uses PBKDF2-HMAC-SHA256 for password
hashing (same algorithm as Django's default hasher).

Storage
-------
The hashed password is stored in ``dashboard_auth.json`` in the project root.
The file never stores the plain-text password.

Lockout
-------
After ``MAX_ATTEMPTS`` consecutive wrong passwords the UI is locked for
``LOCKOUT_SECONDS`` seconds.  Counts are per-session (in-memory).

First run
---------
If no password has been set, the UI shows a "Set Dashboard Password" form
instead of the login form.

Usage in app.py (place at the very top, before any page rendering):

    from dashboard.auth import require_auth
    if not require_auth():
        st.stop()
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional

import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_ROOT         = Path(__file__).resolve().parents[1]   # trading-system/
_AUTH_FILE    = _ROOT / "dashboard_auth.json"
_MAX_ATTEMPTS = 5
_LOCKOUT_SECS = 120   # 2-minute lockout after 5 bad attempts


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------
_ITERATIONS = 260_000   # OWASP 2023 recommendation for PBKDF2-SHA256


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    """Return a ``salt$hash`` string suitable for storage."""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _ITERATIONS,
    )
    return f"{salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    try:
        salt, stored_hash = stored.split("$", 1)
    except ValueError:
        return False
    candidate = _hash_password(password, salt)
    return secrets.compare_digest(candidate, stored)


# ---------------------------------------------------------------------------
# Auth file I/O
# ---------------------------------------------------------------------------
def _load_auth() -> dict:
    if _AUTH_FILE.is_file():
        try:
            return json.loads(_AUTH_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_auth(data: dict) -> None:
    tmp = _AUTH_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(_AUTH_FILE)
    # Restrict to owner-only (no-op on Windows but harmless)
    try:
        import stat
        _AUTH_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def is_password_set() -> bool:
    return bool(_load_auth().get("password_hash"))


def set_password(new_password: str) -> None:
    """Hash and persist a new dashboard password."""
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    data = _load_auth()
    data["password_hash"] = _hash_password(new_password)
    _save_auth(data)


def change_password(old_password: str, new_password: str) -> bool:
    """Change the password; returns False if old_password is wrong."""
    data = _load_auth()
    stored = data.get("password_hash", "")
    if not _verify_password(old_password, stored):
        return False
    data["password_hash"] = _hash_password(new_password)
    _save_auth(data)
    return True


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------
def _session_authenticated() -> bool:
    # Check memory first
    if st.session_state.get("_auth_ok"):
        return True
        
    # Check persistent file for cross-refresh persistence
    data = _load_auth()
    last_active = data.get("last_activity_time", 0.0)
    
    # Auto-logout after 15 minutes (900 seconds)
    if time.time() - last_active < 900.0:
        # Restore session state
        st.session_state["_auth_ok"] = True
        return True
        
    return False

def _update_last_activity() -> None:
    """Update the last activity timestamp to prevent timeout while active."""
    data = _load_auth()
    data["last_activity_time"] = time.time()
    _save_auth(data)

def _session_attempts() -> int:
    return int(st.session_state.get("_auth_attempts", 0))

def _session_lockout_until() -> float:
    return float(st.session_state.get("_auth_lockout_until", 0.0))

# ---------------------------------------------------------------------------
# Main entry point — call this at the top of app.py
# ---------------------------------------------------------------------------
def require_auth() -> bool:
    """Show login / setup form and return True only if the session is authenticated."""
    
    # ── Already authenticated this session ────────────────────────
    if _session_authenticated():
        # Update activity timer on every page load/interaction
        _update_last_activity()
        return True

    # ── First-time setup: no password configured yet ───────────────
    if not is_password_set():
        _render_setup_form()
        return False

    # ── Lockout check ──────────────────────────────────────────────
    if time.monotonic() < _session_lockout_until():
        remaining = int(_session_lockout_until() - time.monotonic())
        st.error(f"🔒 Too many failed attempts. Try again in {remaining} seconds.")
        st.stop()
        return False

    # ── Normal login form ──────────────────────────────────────────
    _render_login_form()
    return False


# ---------------------------------------------------------------------------
# UI components
# ---------------------------------------------------------------------------
def _render_login_form() -> None:
    # Centred card layout
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown("## 🔐 Dashboard Login")
        st.caption("Enter your dashboard password to continue.")
        password = st.text_input("Password", type="password", key="_login_pw")
        if st.button("Login", use_container_width=True, type="primary", key="_login_btn"):
            _handle_login(password)


def _handle_login(password: str) -> None:
    data   = _load_auth()
    stored = data.get("password_hash", "")

    if _verify_password(password, stored):
        st.session_state["_auth_ok"]       = True
        st.session_state["_auth_attempts"] = 0
        data["last_activity_time"] = time.time()
        _save_auth(data)
        
        # Audit the login
        try:
            from shared.security.audit_log import audit, AuditEvent
            audit.log(AuditEvent.DASHBOARD_LOGIN, {"success": True})
        except Exception:
            pass
        st.rerun()
    else:
        attempts = _session_attempts() + 1
        st.session_state["_auth_attempts"] = attempts
        remaining = _MAX_ATTEMPTS - attempts
        # Audit the failure
        try:
            from shared.security.audit_log import audit, AuditEvent
            audit.log(AuditEvent.DASHBOARD_FAIL, {"attempts": attempts}, severity="WARNING")
        except Exception:
            pass
        if attempts >= _MAX_ATTEMPTS:
            st.session_state["_auth_lockout_until"] = time.monotonic() + _LOCKOUT_SECS
            st.error(f"🔒 Too many failed attempts. Locked for {_LOCKOUT_SECS // 60} minutes.")
        else:
            st.error(f"❌ Incorrect password. {remaining} attempt(s) remaining.")


def _render_setup_form() -> None:
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown("## 🛡️ Set Dashboard Password")
        st.info(
            "This is the first time the dashboard is launched. "
            "Set a password to protect access to trading controls."
        )
        st.caption("Minimum 8 characters. Stored as a secure hash — never in plain text.")
        pw1 = st.text_input("New Password",     type="password", key="_setup_pw1")
        pw2 = st.text_input("Confirm Password", type="password", key="_setup_pw2")
        if st.button("Set Password & Login", use_container_width=True, type="primary"):
            if not pw1:
                st.error("Password cannot be empty.")
            elif pw1 != pw2:
                st.error("Passwords do not match.")
            elif len(pw1) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                try:
                    set_password(pw1)
                    st.session_state["_auth_ok"] = True
                    data = _load_auth()
                    data["last_activity_time"] = time.time()
                    _save_auth(data)
                    st.success("✅ Password set. Logging you in…")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to save password: {exc}")


def render_change_password_widget() -> None:
    """Render a 'Change Password' form inside the settings page."""
    with st.expander("🔑 Change Dashboard Password"):
        old = st.text_input("Current Password", type="password", key="_cp_old")
        n1  = st.text_input("New Password",     type="password", key="_cp_new1")
        n2  = st.text_input("Confirm New",      type="password", key="_cp_new2")
        if st.button("Update Password", key="_cp_btn"):
            if n1 != n2:
                st.error("New passwords do not match.")
            elif len(n1) < 8:
                st.error("New password must be at least 8 characters.")
            elif not change_password(old, n1):
                st.error("❌ Current password is incorrect.")
            else:
                st.success("✅ Password changed successfully.")


def render_logout_button() -> None:
    """Render a logout button in the sidebar."""
    if st.sidebar.button("🚪 Logout", key="_logout_btn"):
        try:
            from shared.security.audit_log import audit, AuditEvent
            audit.log(AuditEvent.DASHBOARD_LOGOUT, {})
        except Exception:
            pass
        st.session_state["_auth_ok"] = False
        data = _load_auth()
        data["last_activity_time"] = 0.0
        _save_auth(data)
        st.rerun()
