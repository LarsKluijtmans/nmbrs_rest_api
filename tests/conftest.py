"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from nmbrs_rest.tokens import Token
from tests.helpers import make_token


@pytest.fixture
def token() -> Token:
    return make_token()


@pytest.fixture
def expired_token() -> Token:
    return make_token(expires_in=-10)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Retry backoff is real time; tests should not pay for it."""
    monkeypatch.setattr("nmbrs_rest.transport.time.sleep", lambda _seconds: None)
    yield
