"""Regression tests for brokers/credentials.py's rotate_encryption_key().

Root-cause fix (production-readiness audit finding): the encrypted
broker-credential store had no key-rotation capability at all — the only
way to change the encryption key was to manually delete .broker.key,
which would make every already-stored credential permanently
undecryptable. These tests exercise the real encrypt/decrypt/HMAC code
in an isolated temp directory (monkeypatched module paths, never the
real project's broker_credentials.json/.broker.key).
"""
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import pytest

import brokers.credentials as creds_mod
from brokers.credentials import (
    delete_credentials, list_saved_brokers, load_credentials,
    rotate_encryption_key, save_credentials,
)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Point the module's file-level globals at an isolated temp dir."""
    monkeypatch.setattr(creds_mod, "_CREDS_FILE", tmp_path / "broker_credentials.json")
    monkeypatch.setattr(creds_mod, "_KEY_FILE", tmp_path / ".broker.key")
    monkeypatch.delenv(creds_mod._ENV_KEY_VAR, raising=False)
    return tmp_path


def test_rotation_preserves_decrypted_values(isolated_store):
    save_credentials("fyers", {"client_id": "ABC123", "secret_key": "topsecret"})
    save_credentials("kite", {"api_key": "KITE456"})

    old_key = (isolated_store / ".broker.key").read_bytes()
    old_raw = (isolated_store / "broker_credentials.json").read_bytes()

    count = rotate_encryption_key()

    assert count == 2
    assert load_credentials("fyers") == {"client_id": "ABC123", "secret_key": "topsecret"}
    assert load_credentials("kite") == {"api_key": "KITE456"}

    new_key = (isolated_store / ".broker.key").read_bytes()
    new_raw = (isolated_store / "broker_credentials.json").read_bytes()
    assert new_key != old_key
    assert new_raw != old_raw  # real re-encryption happened, not a no-op copy


def test_old_key_is_backed_up(isolated_store):
    save_credentials("fyers", {"client_id": "ABC123"})
    old_key = (isolated_store / ".broker.key").read_bytes()

    rotate_encryption_key()

    backup = isolated_store / ".broker.key.bak"
    assert backup.exists()
    assert backup.read_bytes() == old_key


def test_rotation_refuses_when_env_key_is_set(isolated_store, monkeypatch):
    save_credentials("fyers", {"client_id": "ABC123"})
    monkeypatch.setenv(creds_mod._ENV_KEY_VAR, "some-externally-managed-key")

    with pytest.raises(RuntimeError, match="environment variable"):
        rotate_encryption_key()

    # Nothing should have been touched.
    assert not (isolated_store / ".broker.key.bak").exists()


def test_rotation_refuses_on_integrity_failure(isolated_store):
    save_credentials("fyers", {"client_id": "ABC123"})
    creds_file = isolated_store / "broker_credentials.json"
    # Corrupt the JSON body while leaving the MAC line intact.
    raw = creds_file.read_bytes()
    json_bytes, mac_part = raw.rsplit(b"\n# MAC:", 1)
    corrupted = json_bytes + b"CORRUPTED" + b"\n# MAC:" + mac_part
    creds_file.write_bytes(corrupted)

    with pytest.raises(RuntimeError, match="integrity check"):
        rotate_encryption_key()

    assert not (isolated_store / ".broker.key.bak").exists()


def test_rotation_with_empty_store_is_a_noop_success(isolated_store):
    # No credentials saved yet — should succeed with count 0, not error.
    count = rotate_encryption_key()
    assert count == 0


def test_rotation_verification_failure_touches_no_files(isolated_store, monkeypatch):
    """Sabotage: make re-encryption silently produce wrong ciphertext (as if
    a bug in _encrypt existed) and confirm rotate_encryption_key detects it
    via its own round-trip check and aborts before writing anything."""
    save_credentials("fyers", {"client_id": "ABC123"})
    old_key_bytes = (isolated_store / ".broker.key").read_bytes()
    old_creds_bytes = (isolated_store / "broker_credentials.json").read_bytes()

    real_decrypt = creds_mod._decrypt

    def broken_decrypt(ciphertext, key=None):
        # Simulate corruption: decrypting under the *new* key returns garbage
        # instead of the real plaintext, as the verification step would see it.
        if key is not None:
            return "CORRUPTED-" + real_decrypt(ciphertext, key=key)
        return real_decrypt(ciphertext, key=key)

    monkeypatch.setattr(creds_mod, "_decrypt", broken_decrypt)

    with pytest.raises(RuntimeError, match="verification failed"):
        rotate_encryption_key()

    assert not (isolated_store / ".broker.key.bak").exists()
    assert (isolated_store / ".broker.key").read_bytes() == old_key_bytes
    assert (isolated_store / "broker_credentials.json").read_bytes() == old_creds_bytes


def test_rotation_leaves_other_brokers_and_delete_working_afterward(isolated_store):
    save_credentials("fyers", {"client_id": "ABC123"})
    save_credentials("kite", {"api_key": "KITE456"})
    rotate_encryption_key()

    assert set(list_saved_brokers()) == {"fyers", "kite"}
    delete_credentials("kite")
    assert set(list_saved_brokers()) == {"fyers"}
    assert load_credentials("fyers") == {"client_id": "ABC123"}
