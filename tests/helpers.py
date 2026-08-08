"""Shared test helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nmbrs_rest.tokens import Token

SUBSCRIPTION_KEY = "30d05593229f49c18856be06ebc47b24"


def make_token(
    *,
    access_token: str = "access-aaa",
    refresh_token: str | None = "refresh-aaa",
    expires_in: int = 3600,
    scopes: tuple[str, ...] = ("company.info.read", "employee.info.read", "offline_access"),
) -> Token:
    """A token that is valid by default; pass a negative ``expires_in`` for expired."""
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in),
        scopes=scopes,
    )
