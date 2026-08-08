"""OAuth 2.0 authorization code flow against identityservice.nmbrs.com.

Nmbrs supports the authorization code flow only. The identity server advertises
other grant types because it is shared across Nmbrs products, but they are not
available to the public REST API.

See ``docs/authentication.md``.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import quote, urlencode

import httpx

from nmbrs_rest.errors import (
    IdentityServerError,
    InvalidClientError,
    InvalidGrantError,
    NmbrsConfigError,
    NmbrsConnectionError,
    NmbrsTimeoutError,
)
from nmbrs_rest.tokens import Token

__all__ = ["AuthorizationRequest", "OAuth", "basic_auth_header"]

IDENTITY_BASE: Final[str] = "https://identityservice.nmbrs.com"

AUTHORIZE_URL: Final[str] = f"{IDENTITY_BASE}/connect/authorize"
TOKEN_URL: Final[str] = f"{IDENTITY_BASE}/connect/token"
PAR_URL: Final[str] = f"{IDENTITY_BASE}/connect/par"
REVOCATION_URL: Final[str] = f"{IDENTITY_BASE}/connect/revocation"

_ERROR_CLASSES: Final[dict[str, type[IdentityServerError]]] = {
    "invalid_grant": InvalidGrantError,
    "invalid_client": InvalidClientError,
}


def basic_auth_header(client_id: str, client_secret: str) -> str:
    """Build the HTTP Basic header for the token endpoint.

    RFC 6749 s2.3.1 requires each half to be percent-encoded *before* joining with
    a colon and base64-encoding. This is not pedantry: Nmbrs credentials routinely
    contain characters like ``*`` and ``$``, and skipping the encoding produces a
    confusing ``invalid_client`` rather than an obvious failure.
    """
    encoded = f"{quote(client_id, safe='')}:{quote(client_secret, safe='')}"
    return "Basic " + base64.b64encode(encoded.encode("utf-8")).decode("ascii")


def _pkce_pair() -> tuple[str, str]:
    """Return ``(verifier, challenge)`` for PKCE S256."""
    verifier = secrets.token_urlsafe(64)[:128]  # RFC 7636: 43-128 chars
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """Everything you must carry from the redirect to the callback.

    ``state`` must be checked against the value returned on the callback, and
    ``code_verifier`` (when PKCE is used) must be passed to :meth:`OAuth.exchange_code`.
    Store both in the user's session.
    """

    url: str
    state: str
    code_verifier: str | None = None


class OAuth:
    """Client for the Nmbrs identity server."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str | None = None,
        *,
        http_client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not client_id or not client_secret:
            raise NmbrsConfigError("client_id and client_secret are required")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._timeout = timeout
        self._client = http_client
        self._owns_client = http_client is None

    # -- internals -------------------------------------------------------- #

    @property
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> OAuth:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        headers = {
            "Authorization": basic_auth_header(self.client_id, self.client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        try:
            response = self._http.post(url, data=data, headers=headers)
        except httpx.TimeoutException as exc:
            raise NmbrsTimeoutError(f"timeout contacting {url}: {exc}") from exc
        except httpx.HTTPError as exc:
            raise NmbrsConnectionError(f"could not reach {url}: {exc}") from exc

        payload: dict[str, Any]
        try:
            parsed = response.json()
            payload = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            payload = {}

        if response.is_error or "error" in payload:
            error = str(payload.get("error") or f"http_{response.status_code}")
            description = payload.get("error_description")
            cls = _ERROR_CLASSES.get(error, IdentityServerError)
            raise cls(
                error,
                str(description) if description else None,
                http_status=response.status_code,
            )
        return payload

    def _require_redirect_uri(self, override: str | None) -> str:
        uri = override or self.redirect_uri
        if not uri:
            raise NmbrsConfigError(
                "redirect_uri is required; pass it to OAuth(...) or to this call"
            )
        return uri

    # -- step 1: authorization -------------------------------------------- #

    def authorization_url(
        self,
        scopes: Sequence[str],
        *,
        state: str | None = None,
        redirect_uri: str | None = None,
        pkce: bool = False,
        par: bool = False,
    ) -> AuthorizationRequest:
        """Build the URL to send the user to.

        Include ``offline_access`` in ``scopes`` or you will not receive a refresh
        token, and the integration will stop working after one hour.

        ``pkce`` uses S256. The identity server advertises PKCE support in its
        discovery document, but Nmbrs does not document it - verify against your
        own client before depending on it.

        ``par`` pushes the parameters over a back channel first, so they never
        appear in a browser-visible URL. It replaces this step only.
        """
        if not scopes:
            raise NmbrsConfigError("at least one scope is required")

        uri = self._require_redirect_uri(redirect_uri)
        state = state or secrets.token_urlsafe(32)
        verifier: str | None = None

        params: dict[str, str] = {
            "client_id": self.client_id,
            "redirect_uri": uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
        }
        if pkce:
            verifier, challenge = _pkce_pair()
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"

        if par:
            payload = self._post_form(PAR_URL, params)
            request_uri = payload.get("request_uri")
            if not request_uri:
                raise IdentityServerError(
                    "invalid_request", "PAR response did not contain a request_uri"
                )
            # After PAR, only these two parameters are sent; the rest are bound to
            # the request_uri server-side.
            url = f"{AUTHORIZE_URL}?" + urlencode(
                {"client_id": self.client_id, "request_uri": str(request_uri)}
            )
        else:
            url = f"{AUTHORIZE_URL}?" + urlencode(params)

        return AuthorizationRequest(url=url, state=state, code_verifier=verifier)

    # -- step 2: exchange -------------------------------------------------- #

    def exchange_code(
        self,
        code: str,
        *,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
        returned_state: str | None = None,
        expected_state: str | None = None,
    ) -> Token:
        """Exchange an authorization code for tokens.

        The code is valid for 5 minutes and single use.

        If both ``returned_state`` and ``expected_state`` are given they must match;
        this is the CSRF check and skipping it is a real vulnerability, so pass them.
        """
        state_supplied = expected_state is not None or returned_state is not None
        if state_supplied and not secrets.compare_digest(
            str(returned_state or ""), str(expected_state or "")
        ):
            raise NmbrsConfigError(
                "OAuth state mismatch: the callback state does not match the one "
                "issued with the authorization request. Treat this as a possible "
                "CSRF attempt and abort the flow."
            )

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._require_redirect_uri(redirect_uri),
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        return Token.from_response(self._post_form(TOKEN_URL, data))

    # -- step 3: refresh --------------------------------------------------- #

    def refresh(self, refresh_token: str) -> Token:
        """Exchange a refresh token for a new token set.

        The returned token carries a **new** refresh token; the one passed in is now
        dead. Persist the result before using it.
        """
        if not refresh_token:
            raise NmbrsConfigError(
                "no refresh token available. This usually means 'offline_access' was "
                "not requested at consent time; re-run the authorization flow with it."
            )
        payload = self._post_form(
            TOKEN_URL, {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )
        token = Token.from_response(payload)
        if token.refresh_token is None:
            # Should not happen, but silently dropping it would strand the caller.
            token = token.model_copy(update={"refresh_token": refresh_token})
        return token

    # -- revocation -------------------------------------------------------- #

    def revoke(self, token: str, *, token_type_hint: str = "refresh_token") -> None:
        """Revoke a token when a customer disconnects.

        Deleting your local copy alone leaves a live credential outstanding for up
        to 30 days.
        """
        self._post_form(REVOCATION_URL, {"token": token, "token_type_hint": token_type_hint})
