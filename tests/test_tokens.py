"""Token model and token stores."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from nmbrs_rest.errors import TokenStoreError
from nmbrs_rest.tokens import CallbackTokenStore, FileTokenStore, MemoryTokenStore, Token
from tests.helpers import make_token


def test_from_response_computes_absolute_expiry() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    token = Token.from_response(
        {
            "access_token": "abc",
            "refresh_token": "def",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "company.info.read offline_access",
        },
        now=now,
    )
    assert token.expires_at == now + timedelta(hours=1)
    assert token.scopes == ("company.info.read", "offline_access")
    assert token.granted_scopes == frozenset({"company.info.read", "offline_access"})


def test_from_response_without_refresh_token() -> None:
    """No offline_access means no refresh token, and that must not crash."""
    token = Token.from_response({"access_token": "abc", "expires_in": 3600})
    assert token.refresh_token is None


def test_from_response_tolerates_a_bad_expires_in() -> None:
    token = Token.from_response({"access_token": "a", "expires_in": "not-a-number"})
    assert token.expires_at > datetime.now(tz=timezone.utc)


def test_is_expired_uses_skew() -> None:
    token = make_token(expires_in=30)  # inside the 60s default skew
    assert token.is_expired()
    assert not token.is_expired(skew=timedelta(seconds=0))


def test_repr_hides_secrets() -> None:
    token = make_token(access_token="super-secret", refresh_token="also-secret")
    for rendered in (repr(token), str(token)):
        assert "super-secret" not in rendered
        assert "also-secret" not in rendered
        assert "has_refresh_token=True" in rendered


def test_token_is_frozen() -> None:
    token = make_token()
    with pytest.raises(ValidationError, match=r"frozen"):
        token.access_token = "changed"


# --------------------------------------------------------------------------- #
# Stores
# --------------------------------------------------------------------------- #


def test_memory_store_roundtrip() -> None:
    store = MemoryTokenStore()
    assert store.load("k") is None
    token = make_token()
    store.save("k", token)
    assert store.load("k") == token
    store.delete("k")
    assert store.load("k") is None


def test_file_store_roundtrip(tmp_path: Path) -> None:
    store = FileTokenStore(tmp_path / "tokens.json")
    token = make_token()
    store.save("acme", token)

    loaded = store.load("acme")
    assert loaded is not None
    assert loaded.access_token == token.access_token
    assert loaded.refresh_token == token.refresh_token
    assert loaded.scopes == token.scopes
    # Absolute expiry must survive the round trip to the second.
    assert abs((loaded.expires_at - token.expires_at).total_seconds()) < 1


def test_file_store_keeps_tenants_separate(tmp_path: Path) -> None:
    store = FileTokenStore(tmp_path / "tokens.json")
    store.save("acme", make_token(access_token="acme-token"))
    store.save("globex", make_token(access_token="globex-token"))

    acme, globex = store.load("acme"), store.load("globex")
    assert acme is not None and globex is not None
    assert acme.access_token == "acme-token"
    assert globex.access_token == "globex-token"

    store.delete("acme")
    assert store.load("acme") is None
    assert store.load("globex") is not None


def test_file_store_survives_a_missing_file(tmp_path: Path) -> None:
    assert FileTokenStore(tmp_path / "nope" / "tokens.json").load("k") is None


def test_file_store_creates_parent_directories(tmp_path: Path) -> None:
    store = FileTokenStore(tmp_path / "deep" / "nested" / "tokens.json")
    store.save("k", make_token())
    assert (tmp_path / "deep" / "nested" / "tokens.json").exists()


def test_file_store_write_is_atomic(tmp_path: Path) -> None:
    """No .tmp files may be left behind, and the JSON must be complete."""
    path = tmp_path / "tokens.json"
    store = FileTokenStore(path)
    store.save("k", make_token())

    leftovers = [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
    assert "k" in json.loads(path.read_text(encoding="utf-8"))


def test_corrupt_file_raises_an_actionable_error(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(TokenStoreError, match="not valid JSON"):
        FileTokenStore(path).load("k")


def test_empty_file_is_treated_as_absent(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text("", encoding="utf-8")
    assert FileTokenStore(path).load("k") is None


def test_callback_store_delegates() -> None:
    saved: dict[str, Token] = {}

    def _save(key: str, value: Token) -> None:
        saved[key] = value

    def _delete(key: str) -> None:
        saved.pop(key, None)

    store = CallbackTokenStore(load=saved.get, save=_save, delete=_delete)
    token = make_token()
    store.save("k", token)
    assert saved["k"] == token
    assert store.load("k") == token
    store.delete("k")
    assert store.load("k") is None
