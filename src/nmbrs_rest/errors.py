"""Exception hierarchy and the response-to-exception mapper.

The contract this implements is documented in ``docs/errors.md``. Two rules matter
most:

* The documented numeric code list is **not** exhaustive, so mapping degrades to a
  sensible class rather than failing on an unknown code.
* Nothing here ever renders a token. Redaction happens at construction.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "APIError",
    "AuthenticationError",
    "CompanyNotFoundError",
    "DataAccessError",
    "IdentityServerError",
    "InsufficientScopeError",
    "InvalidClientError",
    "InvalidGrantError",
    "InvalidParam",
    "InvalidRequestError",
    "InvalidTokenError",
    "MissingTokenError",
    "NmbrsConfigError",
    "NmbrsConnectionError",
    "NmbrsError",
    "NmbrsTimeoutError",
    "NotAuthenticatedError",
    "NotFoundError",
    "PermissionError",
    "QuotaExceededError",
    "RateLimitError",
    "ReauthorizationRequired",
    "ResourceNotFoundError",
    "ServerError",
    "SubscriptionError",
    "TokenStoreError",
    "TransportError",
    "ValidationError",
    "exception_for",
    "redact",
]


# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #

_SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # Bearer <token>
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    # JWTs anywhere, including bare
    re.compile(r"\beyJ[A-Za-z0-9._-]{16,}"),
    # key=value / "key": "value" for anything secret-shaped
    re.compile(
        r'(?i)("?(?:access_token|refresh_token|client_secret|code_verifier|'
        r'subscription[-_]?key|authorization)"?\s*[:=]\s*"?)([^"\s,&}]+)'
    ),
)

_REDACTED: Final[str] = "[REDACTED]"


def redact(text: str) -> str:
    """Strip anything token-shaped from ``text``.

    Applied to every message this module constructs. It is deliberately eager:
    over-redacting a log line is recoverable, leaking a refresh token is not.
    """
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda m: f"{m.group(1)}{_REDACTED}", text)
        else:
            text = pattern.sub(
                lambda m: f"{m.group(1)}{_REDACTED}" if m.groups() else _REDACTED, text
            )
    return text


# --------------------------------------------------------------------------- #
# Supporting types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class InvalidParam:
    """One entry from the ``invalid-params`` array (note: hyphenated upstream)."""

    name: str
    reason: str

    def __str__(self) -> str:
        return f"{self.name}: {self.reason}"


@dataclass(frozen=True, slots=True)
class Operation:
    """The call being attempted, for error messages and scope diagnosis."""

    method: str
    #: Templated path as it appears in the spec, e.g. ``/api/companies/{companyId}``.
    template: str
    #: Concrete path actually requested.
    path: str = ""
    #: Scopes the token was *granted* (not the ones requested at consent).
    granted_scopes: frozenset[str] = field(default_factory=frozenset)

    def __str__(self) -> str:
        return f"{self.method} {self.path or self.template}"


# --------------------------------------------------------------------------- #
# Roots
# --------------------------------------------------------------------------- #


class NmbrsError(Exception):
    """Base for everything this SDK raises."""


class NmbrsConfigError(NmbrsError):
    """The SDK was constructed wrongly. Raised before any request is sent."""


class TokenStoreError(NmbrsError):
    """A token store operation failed.

    Raised from ``save()`` this is serious: a rotated refresh token may have been
    lost, which is unrecoverable without re-consent.
    """


class NotAuthenticatedError(NmbrsError):
    """A request was attempted before there was any token to send.

    Nmbrs supports the authorization code flow only, so the first token always
    requires a human to approve in a browser.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or (
                "not authenticated. Either finish the authorization flow:\n"
                "    url = api.login(redirect_uri, scopes)   # send the user here\n"
                "    api.authenticate(code)                  # code from the redirect\n"
                "or construct with a refresh token you saved earlier:\n"
                "    Nmbrs(client_id, client_secret, subscription_key, "
                "refresh_token=...)"
            )
        )


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #


class TransportError(NmbrsError):
    """No usable HTTP response was obtained."""


class NmbrsTimeoutError(TransportError):
    """A connect or read timeout.

    A timeout on a write does **not** mean the write did not happen. Never retry a
    non-idempotent request on this without checking state first.
    """


class NmbrsConnectionError(TransportError):
    """DNS failure, TLS failure, connection reset, or proxy error."""


# --------------------------------------------------------------------------- #
# Identity server (RFC 6749) - distinct from API errors (RFC 7807)
# --------------------------------------------------------------------------- #


class IdentityServerError(NmbrsError):
    """An OAuth error from identityservice.nmbrs.com.

    Deliberately **not** a subclass of :class:`APIError`: a different system
    rejected you, with a different payload shape and different remedies.
    """

    def __init__(
        self,
        error: str,
        description: str | None = None,
        *,
        http_status: int | None = None,
    ) -> None:
        self.error = error
        self.description = description
        self.http_status = http_status
        message = f"{error}: {description}" if description else error
        super().__init__(redact(message))


class InvalidClientError(IdentityServerError):
    """Wrong client_id/client_secret, or a Basic header that was not percent-encoded.

    See ``docs/authentication.md`` - RFC 6749 s2.3.1 requires each half to be
    URL-encoded *before* joining and base64-encoding.
    """


class InvalidGrantError(IdentityServerError):
    """Refresh token expired, already used, or consent revoked.

    Before treating this as terminal, reload from the token store: a concurrent
    worker may simply have rotated the token first.
    """


class ReauthorizationRequired(IdentityServerError):
    """Terminal. The end user must go through the consent flow again."""

    def __init__(self, reason: str, *, token_key: str | None = None) -> None:
        self.token_key = token_key
        where = f" (token_key={token_key!r})" if token_key else ""
        super().__init__(
            "reauthorization_required",
            f"{reason}{where}. The user must authorize the integration again.",
        )


# --------------------------------------------------------------------------- #
# API errors (RFC 7807)
# --------------------------------------------------------------------------- #


class APIError(NmbrsError):
    """An RFC 7807 error response from api.nmbrsapp.com."""

    def __init__(
        self,
        *,
        http_status: int,
        code: int | None = None,
        title: str | None = None,
        detail: str | None = None,
        type_: str | None = None,
        invalid_params: tuple[InvalidParam, ...] = (),
        doc_url: str | None = None,
        operation: Operation | None = None,
        request_id: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.http_status = http_status
        self.code = code
        self.title = title
        self.detail = detail
        self.type = type_
        self.invalid_params = invalid_params
        self.doc_url = doc_url
        self.operation = operation
        self.request_id = request_id
        self.hint = hint
        super().__init__(self._render())

    @property
    def method(self) -> str | None:
        return self.operation.method if self.operation else None

    @property
    def path(self) -> str | None:
        if self.operation is None:
            return None
        return self.operation.path or self.operation.template

    def _render(self) -> str:
        marker = f"{self.http_status}" if self.code is None else f"{self.http_status}/{self.code}"
        where = str(self.operation) if self.operation else "request"
        body = self.detail or self.title or "no detail provided"
        message = f"[{marker}] {where}: {body}"
        for param in self.invalid_params:
            message += f"\n  - {param}"
        if self.hint:
            message += f"\n\n{self.hint}"
        return redact(message)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(http_status={self.http_status!r}, "
            f"code={self.code!r}, title={self.title!r})"
        )


class AuthenticationError(APIError):
    """401. The request was not authenticated."""


class MissingTokenError(AuthenticationError):
    """40101. No Authorization header arrived."""


class InvalidTokenError(AuthenticationError):
    """40102. Access token expired, malformed, or revoked.

    Normally invisible: the transport refreshes once and replays.
    """


class PermissionError(APIError):
    """403. Authenticated, but not allowed."""


class InsufficientScopeError(PermissionError):
    """403 where the token was never granted a scope that satisfies the operation.

    Detected locally by comparing the operation's required scopes against the
    granted scopes on the token, so the message can name both.
    """

    def __init__(self, *, missing: frozenset[str], **kwargs: Any) -> None:
        self.missing = missing
        operation: Operation | None = kwargs.get("operation")
        granted = sorted(operation.granted_scopes) if operation else []
        kwargs.setdefault("detail", "missing required scope")
        kwargs["hint"] = (
            f"  This operation accepts any of:  {', '.join(sorted(missing))}\n"
            f"  Your token was granted:         {', '.join(granted) or '(none recorded)'}\n\n"
            f"  Scope is fixed at consent time and cannot be widened for an existing\n"
            f"  token. Re-run the authorization flow including one of the scopes above."
        )
        super().__init__(**kwargs)


class DataAccessError(PermissionError):
    """40303 / 40305. Scope is fine; the consenting login cannot see this data.

    In multi-tenant applications this most often means a token consented for one
    debtor was used against another debtor's company.
    """


class SubscriptionError(PermissionError):
    """40304. The customer's Nmbrs environment is disabled."""


class NotFoundError(APIError):
    """404."""


class ResourceNotFoundError(NotFoundError):
    """40401, or an empty ``data`` array on a single-item read."""


class CompanyNotFoundError(NotFoundError):
    """40404. The companyId path parameter did not resolve."""


class ValidationError(APIError):
    """400 validationError. Field-level validation failed; see ``invalid_params``."""


class InvalidRequestError(APIError):
    """400 invalidRequestError. Rejected by a business rule."""


class RateLimitError(APIError):
    """429. Throttled. Retryable with backoff."""

    #: Seconds to wait, if the response carried a Retry-After header.
    retry_after: float | None = None


class QuotaExceededError(RateLimitError):
    """42909. Plan call volume exhausted.

    **Not** retryable: the quota resets on a billing cycle, not in seconds.
    """


class ServerError(APIError):
    """500, 502, 503. 502 and 503 are usually transient; 500 usually is not."""


# --------------------------------------------------------------------------- #
# Mapping
# --------------------------------------------------------------------------- #

_BY_CODE: Final[dict[int, type[APIError]]] = {
    40033: ValidationError,
    40101: MissingTokenError,
    40102: InvalidTokenError,
    40303: DataAccessError,
    40304: SubscriptionError,
    40305: DataAccessError,
    40401: ResourceNotFoundError,
    40404: CompanyNotFoundError,
    42908: RateLimitError,
    42909: QuotaExceededError,
    50001: ServerError,
    50201: ServerError,
    50301: ServerError,
}

_BY_TYPE: Final[dict[str, type[APIError]]] = {
    "invalidRequestError": InvalidRequestError,
    "validationError": ValidationError,
    # Nmbrs' prose docs say `rateLimitError`; every spec example says
    # `throttlingError`. Accept both.
    "throttlingError": RateLimitError,
    "rateLimitError": RateLimitError,
    "apiError": ServerError,
}

_BY_STATUS: Final[dict[int, type[APIError]]] = {
    400: ValidationError,
    401: AuthenticationError,
    403: PermissionError,
    404: NotFoundError,
    429: RateLimitError,
    500: ServerError,
    502: ServerError,
    503: ServerError,
}


def parse_problem(body: bytes | str, content_type: str | None = None) -> dict[str, Any]:
    """Best-effort RFC 7807 parse.

    Must never raise. Gateways return HTML on 502/503 and bodies are sometimes
    empty; a JSONDecodeError here would mask the real failure.
    """
    if content_type and "json" not in content_type.lower():
        return {}
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _invalid_params(payload: dict[str, Any]) -> tuple[InvalidParam, ...]:
    raw = payload.get("invalid-params") or payload.get("invalid_params") or []
    if not isinstance(raw, list):
        return ()
    out: list[InvalidParam] = []
    for entry in raw:
        if isinstance(entry, dict):
            out.append(
                InvalidParam(
                    name=str(entry.get("name", "?")),
                    reason=str(entry.get("reason", "invalid")),
                )
            )
    return tuple(out)


def missing_scopes(operation: Operation | None) -> frozenset[str]:
    """Scopes that would satisfy ``operation``, none of which the token holds.

    Empty when the operation is satisfied, unknown, or no granted scopes were
    recorded (in which case we cannot claim a scope problem).
    """
    if operation is None or not operation.granted_scopes:
        return frozenset()

    from nmbrs_rest._scopes import REQUIRED_SCOPES

    required = REQUIRED_SCOPES.get((operation.method, operation.template), frozenset())
    if not required or required & operation.granted_scopes:
        return frozenset()
    return required


def exception_for(
    *,
    status_code: int,
    body: bytes | str = b"",
    content_type: str | None = None,
    operation: Operation | None = None,
    request_id: str | None = None,
    retry_after: float | None = None,
) -> APIError:
    """Map an HTTP error response onto the most specific exception available.

    Precedence: numeric code, then ``type``, then HTTP status. The status fallback
    means an undocumented code still lands somewhere useful.
    """
    payload = parse_problem(body, content_type)
    raw_code = payload.get("code")
    code = raw_code if isinstance(raw_code, int) else None
    type_ = payload.get("type") if isinstance(payload.get("type"), str) else None

    cls: type[APIError] | None = _BY_CODE.get(code) if code is not None else None

    # `authenticationError` covers both 401 and 403 upstream; split on status.
    if cls is None and type_ == "authenticationError":
        cls = AuthenticationError if status_code == 401 else PermissionError
    if cls is None and type_ is not None:
        cls = _BY_TYPE.get(type_)
    if cls is None:
        cls = _BY_STATUS.get(status_code, APIError)

    common: dict[str, Any] = {
        "http_status": status_code,
        "code": code,
        "title": payload.get("title") if isinstance(payload.get("title"), str) else None,
        "detail": payload.get("detail") if isinstance(payload.get("detail"), str) else None,
        "type_": type_,
        "invalid_params": _invalid_params(payload),
        "doc_url": payload.get("docUrl") if isinstance(payload.get("docUrl"), str) else None,
        "operation": operation,
        "request_id": request_id,
    }

    if status_code == 403:
        missing = missing_scopes(operation)
        if missing:
            return InsufficientScopeError(missing=missing, **common)
        # Scope is satisfied, so this is a data-access restriction. Say so, since
        # the remedy is the customer's admin rather than a code change.
        #
        # SubscriptionError (40304) is excluded: a disabled environment has nothing
        # to do with scope, and the hint would be actively misleading.
        if (
            issubclass(cls, PermissionError)
            and not issubclass(cls, SubscriptionError)
            and operation is not None
            and operation.granted_scopes
        ):
            common["hint"] = (
                "  The required scope IS granted, so this is not a scope problem.\n"
                "  The consenting Nmbrs login cannot see this debtor or company.\n"
                "  Either the token was consented for a different debtor, or the login\n"
                "  needs its access rights (tags/filters) reviewed in Nmbrs."
            )

    error = cls(**common)
    if isinstance(error, RateLimitError):
        error.retry_after = retry_after
    return error
