"""Securely add, update, or rotate encrypted broker credentials.

Root-cause fix (2026-08-15): this script used to collect only the fields
for a hardcoded broker template and call save_credentials(broker, creds)
with just those -- but save_credentials() REPLACES the whole stored
credential dict for that broker_id, it doesn't merge. Running this for a
partial update (e.g. rotating just client_id/secret_key on the Fyers
developer portal) would have silently wiped out every other already-saved
field (fyers_user_id, fyers_pin, fyers_totp_key) with no warning. Now
loads existing credentials first, shows which fields are already set
(never their values), and leaves anything you press Enter on unchanged.

Also now: masks secret-like input (secret_key, pin, totp keys, password)
so it isn't echoed to the terminal; for fyers specifically, tests the
new credentials via the real auto-login flow before committing, and
rolls back to the previous credentials on failure so a typo can never
leave the live system unable to authenticate; and, after a successful
client_id/secret_key change, offers to keep .env's FYERS_CLIENT_ID/
FYERS_SECRET_KEY in sync (used by the dashboard's password-reset
identity check and the separate manual `trading_bot.login` flow, both
of which read from .env independently of broker_credentials.json).

Run from the trading-system/ directory:
    python scripts/auth/save_broker_creds.py
"""
import getpass
import sys
from pathlib import Path

# Add project root to path so we can import brokers module
sys.path.append(str(Path(__file__).resolve().parents[1]))

from brokers.credentials import load_credentials, save_credentials

_SECRET_FIELDS = {"secret_key", "api_secret", "pin", "password", "totp_secret", "fyers_totp_key", "fyers_pin"}

_BROKER_FIELDS = {
    "fyers": ["client_id", "secret_key", "redirect_uri"],
    "kite": ["api_key", "api_secret"],
    "angel": ["api_key", "client_code", "password"],
}


def _prompt_field(key: str, already_set: bool) -> str | None:
    """Prompt for one field. Returns None (meaning "leave unchanged") if
    the user presses Enter with nothing typed and a value already exists;
    for a field with no existing value, an empty answer is not allowed."""
    label = key.replace("_", " ").title()
    hint = " [Enter to keep existing]" if already_set else ""
    reader = getpass.getpass if key in _SECRET_FIELDS else input
    prompt = f"Enter {label}{hint}: "
    value = reader(prompt).strip()
    if not value:
        return None if already_set else ""
    return value


def _collect_updates(broker: str, existing: dict) -> dict:
    fields = _BROKER_FIELDS.get(broker)
    updates: dict = {}
    if fields:
        for key in fields:
            val = _prompt_field(key, already_set=bool(existing.get(key)))
            if val:
                updates[key] = val
    else:
        print("Custom broker — enter key/value pairs to add or update (blank key to finish).")
        while True:
            key = input("Field name (blank to finish): ").strip()
            if not key:
                break
            val = _prompt_field(key, already_set=bool(existing.get(key)))
            if val:
                updates[key] = val
    return updates


def _sync_dotenv_fyers(client_id: str | None, secret_key: str | None) -> None:
    """Keep .env's FYERS_CLIENT_ID/FYERS_SECRET_KEY in sync with what was
    just saved to the encrypted store, so the dashboard's password-reset
    identity check (api_bridge.py's /api/auth/reset) and the separate
    manual `python -m trading_bot.login` flow don't silently authenticate
    against a stale, pre-rotation value."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        print("(.env not found -- skipping sync)")
        return
    lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
    updated = {"FYERS_CLIENT_ID": client_id, "FYERS_SECRET_KEY": secret_key}
    updated = {k: v for k, v in updated.items() if v}
    if not updated:
        return
    seen = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        matched = False
        for key, val in updated.items():
            if stripped.startswith(f"{key}=") and key not in seen:
                new_lines.append(f"{key}={val}")
                seen.add(key)
                matched = True
                break
        if not matched:
            new_lines.append(line)
    for key, val in updated.items():
        if key not in seen:
            new_lines.append(f"{key}={val}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"✓ .env updated ({', '.join(updated.keys())}) to match the new credentials.")


def main() -> None:
    print("=== Secure Broker Credential Manager ===")
    print("Values are encrypted at rest (Fernet + HMAC integrity check).")
    print("Existing fields you don't want to change: press Enter to keep them.")
    print("------------------------------------------------")

    broker = input("Enter Broker ID (e.g., fyers, kite, angel): ").strip().lower()
    if not broker:
        print("Broker ID cannot be empty.")
        return

    existing = load_credentials(broker)
    if existing:
        print(f"\nExisting saved fields for '{broker}': {', '.join(sorted(existing.keys()))} (values hidden)")
    else:
        print(f"\nNo credentials currently saved for '{broker}'.")

    updates = _collect_updates(broker, existing)
    if not updates:
        print("✖ No changes entered. Aborting — nothing was touched.")
        return

    merged = dict(existing)
    merged.update(updates)

    print("\nSaving and encrypting credentials...")
    save_credentials(broker, merged)

    if broker == "fyers" and {"client_id", "secret_key"} & updates.keys():
        print("Verifying the new credentials with a real login attempt...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/auth/auto_login_fyers.py"],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]),
        )
        if result.returncode != 0:
            print("✖ Login test FAILED with the new credentials — rolling back.")
            print(result.stdout.strip())
            print(result.stderr.strip())
            if existing:
                save_credentials(broker, existing)
                print("Previous credentials restored. Nothing else was changed.")
            else:
                from brokers.credentials import delete_credentials
                delete_credentials(broker)
                print("No previous credentials existed — new (broken) ones removed.")
            return
        print("✓ Login test succeeded with the new credentials.")

        sync = input("\nAlso update .env's FYERS_CLIENT_ID/FYERS_SECRET_KEY to match? [Y/n]: ").strip().lower()
        if sync in ("", "y", "yes"):
            _sync_dotenv_fyers(updates.get("client_id"), updates.get("secret_key"))

    print(f"\n✓ Success! Credentials updated for '{broker}': {', '.join(sorted(updates.keys()))}.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
    except Exception as e:
        print(f"\nError: {e}")
