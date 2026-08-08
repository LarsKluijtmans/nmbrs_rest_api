"""OAuth flow mechanics."""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from nmbrs_rest.auth import PAR_URL, TOKEN_URL, OAuth, basic_auth_header
from nmbrs_rest.errors import (
    IdentityServerError,
    InvalidClientError,
    InvalidGrantError,
    NmbrsConfigError,
)

CLIENT_ID = "7xr7NV9yqcUz*r2C$ey6"
CLIENT_SECRET = "s3cr3t/w1th+chars="
REDIRECT = "https://app.example/callback"
SCOPES = ("company.info.read", "offline_access")


@pytest.fixture
def oauth() -> OAuth:
    return OAuth(CLIENT_ID, CLIENT_SECRET, REDIRECT)


# --------------------------------------------------------------------------- #
# The Basic auth footgun
# --------------------------------------------------------------------------- #


def test_basic_auth_percent_encodes_each_half_before_joining() -> None:
    """RFC 6749 s2.3.1. Nmbrs credentials really do contain * and $."""
    header = basic_auth_header(CLIENT_ID, CLIENT_SECRET)
    decoded = base64.b64decode(header.removeprefix("Basic ")).decode()

    assert decoded == "7xr7NV9yqcUz%2Ar2C%24ey6:s3cr3t%2Fw1th%2Bchars%3D"
    # The naive version would have produced this instead.
    assert decoded != f"{CLIENT_ID}:{CLIENT_SECRET}"


def test_basic_auth_splits_on_exactly_one_colon() -> None:
    """Encoding first is what guarantees the separator is unambiguous."""
    decoded = base64.b64decode(
        basic_auth_header("id:with:colons", "secret:too").removeprefix("Basic ")
    ).decode()
    assert decoded.count(":") == 1


# --------------------------------------------------------------------------- #
# Step 1
# --------------------------------------------------------------------------- #


def test_authorization_url_contains_every_required_parameter(oauth: OAuth) -> None:
    request = oauth.authorization_url(SCOPES)
    query = parse_qs(urlparse(request.url).query)

    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [REDIRECT]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["company.info.read offline_access"]  # space separated
    assert query["state"] == [request.state]
    assert request.code_verifier is None


def test_state_is_generated_and_unpredictable(oauth: OAuth) -> None:
    states = {oauth.authorization_url(SCOPES).state for _ in range(10)}
    assert len(states) == 10


def test_pkce_uses_s256_and_returns_the_verifier(oauth: OAuth) -> None:
    request = oauth.authorization_url(SCOPES, pkce=True)
    query = parse_qs(urlparse(request.url).query)

    assert query["code_challenge_method"] == ["S256"]
    assert request.code_verifier is not None
    assert 43 <= len(request.code_verifier) <= 128

    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(request.code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert query["code_challenge"] == [expected]


def test_scopes_are_required(oauth: OAuth) -> None:
    with pytest.raises(NmbrsConfigError, match="at least one scope"):
        oauth.authorization_url([])


def test_redirect_uri_is_required() -> None:
    with pytest.raises(NmbrsConfigError, match="redirect_uri is required"):
        OAuth(CLIENT_ID, CLIENT_SECRET).authorization_url(SCOPES)


@respx.mock
def test_par_pushes_parameters_and_shortens_the_redirect(oauth: OAuth) -> None:
    route = respx.post(PAR_URL).mock(
        return_value=httpx.Response(200, json={"request_uri": "urn:x:abc", "expires_in": 600})
    )
    request = oauth.authorization_url(SCOPES, par=True)

    pushed = parse_qs(route.calls[0].request.content.decode())
    assert pushed["scope"] == ["company.info.read offline_access"]
    assert pushed["response_type"] == ["code"]

    query = parse_qs(urlparse(request.url).query)
    assert query == {"client_id": [CLIENT_ID], "request_uri": ["urn:x:abc"]}
    assert "scope" not in query  # the whole point of PAR


@respx.mock
def test_par_without_request_uri_is_an_error(oauth: OAuth) -> None:
    respx.post(PAR_URL).mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(IdentityServerError, match="request_uri"):
        oauth.authorization_url(SCOPES, par=True)


# --------------------------------------------------------------------------- #
# Step 2 and 3
# --------------------------------------------------------------------------- #


@respx.mock
def test_exchange_code_returns_a_token(oauth: OAuth) -> None:
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": "company.info.read offline_access",
            },
        )
    )
    token = oauth.exchange_code("the-code")

    body = parse_qs(route.calls[0].request.content.decode())
    assert body["grant_type"] == ["authorization_code"]
    assert body["code"] == ["the-code"]
    assert body["redirect_uri"] == [REDIRECT]
    assert token.access_token == "at"
    assert token.scopes == ("company.info.read", "offline_access")


@respx.mock
def test_exchange_code_sends_the_pkce_verifier(oauth: OAuth) -> None:
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
    )
    oauth.exchange_code("c", code_verifier="the-verifier")
    assert parse_qs(route.calls[0].request.content.decode())["code_verifier"] == ["the-verifier"]


def test_state_mismatch_is_rejected(oauth: OAuth) -> None:
    with pytest.raises(NmbrsConfigError, match="state mismatch"):
        oauth.exchange_code("c", returned_state="attacker", expected_state="ours")


@respx.mock
def test_matching_state_is_accepted(oauth: OAuth) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
    )
    assert oauth.exchange_code("c", returned_state="s", expected_state="s").access_token == "at"


@respx.mock
def test_refresh_rotates_the_refresh_token(oauth: OAuth) -> None:
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "at2", "refresh_token": "rt2", "expires_in": 3600}
        )
    )
    token = oauth.refresh("rt1")

    body = parse_qs(route.calls[0].request.content.decode())
    assert body["grant_type"] == ["refresh_token"]
    assert body["refresh_token"] == ["rt1"]
    assert token.refresh_token == "rt2"  # rotated


@respx.mock
def test_refresh_keeps_the_old_token_if_none_is_returned(oauth: OAuth) -> None:
    """Defensive: silently dropping it would strand the caller."""
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at2", "expires_in": 3600})
    )
    assert oauth.refresh("rt1").refresh_token == "rt1"


def test_refresh_without_a_token_explains_offline_access(oauth: OAuth) -> None:
    with pytest.raises(NmbrsConfigError, match="offline_access"):
        oauth.refresh("")


# --------------------------------------------------------------------------- #
# RFC 6749 errors
# --------------------------------------------------------------------------- #


@respx.mock
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("invalid_grant", InvalidGrantError),
        ("invalid_client", InvalidClientError),
        ("invalid_scope", IdentityServerError),
        ("access_denied", IdentityServerError),
    ],
)
def test_identity_server_errors_map(
    oauth: OAuth, error: str, expected: type[IdentityServerError]
) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": error, "error_description": "because"})
    )
    with pytest.raises(expected) as exc_info:
        oauth.refresh("rt")
    assert exc_info.value.error == error
    assert exc_info.value.description == "because"


@respx.mock
def test_non_json_identity_error_still_raises(oauth: OAuth) -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(500, text="<html>boom</html>"))
    with pytest.raises(IdentityServerError, match="http_500"):
        oauth.refresh("rt")
