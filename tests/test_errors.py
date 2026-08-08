"""Error mapping, redaction and scope diagnosis."""

from __future__ import annotations

import json

import pytest

from nmbrs_rest.errors import (
    APIError,
    CompanyNotFoundError,
    DataAccessError,
    InsufficientScopeError,
    InvalidTokenError,
    MissingTokenError,
    NotFoundError,
    Operation,
    PermissionError,
    QuotaExceededError,
    RateLimitError,
    ResourceNotFoundError,
    ServerError,
    SubscriptionError,
    ValidationError,
    exception_for,
    redact,
)


def problem(**kwargs: object) -> bytes:
    return json.dumps(kwargs).encode()


# --------------------------------------------------------------------------- #
# Code mapping - every documented code
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("status", "code", "type_", "expected"),
    [
        (400, 40033, "validationError", ValidationError),
        (401, 40101, "authenticationError", MissingTokenError),
        (401, 40102, "authenticationError", InvalidTokenError),
        (403, 40303, "authenticationError", DataAccessError),
        (403, 40304, "authenticationError", SubscriptionError),
        (403, 40305, "authenticationError", DataAccessError),
        (404, 40401, "invalidRequestError", ResourceNotFoundError),
        (404, 40404, "invalidRequestError", CompanyNotFoundError),
        (429, 42908, "throttlingError", RateLimitError),
        (429, 42909, "throttlingError", QuotaExceededError),
        (500, 50001, "apiError", ServerError),
        (502, 50201, "apiError", ServerError),
        (503, 50301, "apiError", ServerError),
    ],
)
def test_documented_codes_map_to_specific_exceptions(
    status: int, code: int, type_: str, expected: type[APIError]
) -> None:
    error = exception_for(
        status_code=status,
        body=problem(code=code, type=type_, title="T", detail="D"),
        content_type="application/json",
    )
    assert type(error) is expected
    assert error.code == code
    assert error.http_status == status


def test_quota_exceeded_is_a_rate_limit_error() -> None:
    """Callers catching RateLimitError must still see it, but it is not retryable."""
    error = exception_for(status_code=429, body=problem(code=42909, type="throttlingError"))
    assert isinstance(error, RateLimitError)
    assert isinstance(error, QuotaExceededError)


# --------------------------------------------------------------------------- #
# Graceful degradation - the documented list is not exhaustive
# --------------------------------------------------------------------------- #


def test_unknown_code_falls_back_to_type() -> None:
    error = exception_for(
        status_code=400,
        body=problem(code=49999, type="invalidRequestError", detail="nope"),
        content_type="application/json",
    )
    assert error.code == 49999
    assert error.detail == "nope"


def test_unknown_everything_falls_back_to_status() -> None:
    error = exception_for(status_code=404, body=b"", content_type=None)
    assert type(error) is NotFoundError


def test_rate_limit_error_type_alias_is_accepted() -> None:
    """Nmbrs prose says rateLimitError; the spec examples say throttlingError."""
    for type_ in ("rateLimitError", "throttlingError"):
        error = exception_for(status_code=429, body=problem(type=type_))
        assert isinstance(error, RateLimitError), type_


def test_html_error_body_does_not_explode() -> None:
    """Gateways return HTML on 502/503; parsing must never mask the real failure."""
    error = exception_for(
        status_code=503,
        body=b"<html><head><title>503</title></head><body>upstream</body></html>",
        content_type="text/html",
    )
    assert isinstance(error, ServerError)
    assert error.code is None


def test_empty_and_truncated_bodies() -> None:
    assert exception_for(status_code=500, body=b"").http_status == 500
    assert exception_for(status_code=500, body=b'{"code": 500').http_status == 500


def test_hyphenated_invalid_params_are_surfaced() -> None:
    error = exception_for(
        status_code=400,
        body=problem(
            code=40033,
            type="validationError",
            detail="Invalid parameter.",
            **{"invalid-params": [{"name": "year", "reason": "must be a valid year"}]},
        ),
        content_type="application/json",
    )
    assert len(error.invalid_params) == 1
    assert error.invalid_params[0].name == "year"
    assert "year: must be a valid year" in str(error)


# --------------------------------------------------------------------------- #
# Scope-aware 403
# --------------------------------------------------------------------------- #


def test_missing_scope_produces_insufficient_scope_error() -> None:
    operation = Operation(
        method="GET",
        template="/api/companies/{companyId}/employees/salaries",
        path="/api/companies/abc/employees/salaries",
        granted_scopes=frozenset({"company.info.read", "employee.info.read"}),
    )
    error = exception_for(status_code=403, body=problem(code=40303), operation=operation)

    assert isinstance(error, InsufficientScopeError)
    # Verified against the spec: salaries is employment-scoped, not payment-scoped.
    assert error.missing == frozenset({"employee.employment", "employee.employment.read"})
    message = str(error)
    assert "employee.employment.read" in message
    assert "company.info.read" in message


def test_granted_scope_means_data_access_not_scope() -> None:
    operation = Operation(
        method="GET",
        template="/api/companies/{companyId}/employees/salaries",
        path="/api/companies/abc/employees/salaries",
        granted_scopes=frozenset({"employee.employment.read"}),
    )
    error = exception_for(
        status_code=403,
        body=problem(code=40303, type="authenticationError", detail="No access"),
        operation=operation,
    )
    assert isinstance(error, DataAccessError)
    assert not isinstance(error, InsufficientScopeError)


def test_no_recorded_scopes_does_not_claim_a_scope_problem() -> None:
    """Without granted scopes we cannot know, so do not guess."""
    operation = Operation(
        method="GET",
        template="/api/companies/{companyId}/employees/salaries",
        granted_scopes=frozenset(),
    )
    error = exception_for(status_code=403, body=problem(), operation=operation)
    assert isinstance(error, PermissionError)
    assert not isinstance(error, InsufficientScopeError)


def test_unknown_operation_template_is_not_a_scope_problem() -> None:
    operation = Operation(
        method="GET",
        template="/api/not/a/real/endpoint",
        granted_scopes=frozenset({"company.info.read"}),
    )
    error = exception_for(status_code=403, body=problem(), operation=operation)
    assert not isinstance(error, InsufficientScopeError)


def test_write_scope_satisfies_a_read_operation() -> None:
    operation = Operation(
        method="GET",
        template="/api/companies/{companyId}/employees/contracts",
        granted_scopes=frozenset({"employee.employment"}),  # write implies read
    )
    error = exception_for(status_code=403, body=problem(), operation=operation)
    assert not isinstance(error, InsufficientScopeError)


# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig",
        '{"access_token": "eyJhbGciOiJIUzI1NiJ9abcdefghijklmnop"}',
        '{"refresh_token": "A1B2C3D4E5F6G7H8"}',
        "client_secret=7xr7NV9yqcUz",
    ],
)
def test_redaction_removes_secrets(text: str) -> None:
    cleaned = redact(text)
    assert "[REDACTED]" in cleaned
    for secret in ("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9", "A1B2C3D4E5F6G7H8", "7xr7NV9yqcUz"):
        assert secret not in cleaned


def test_exception_message_never_leaks_a_token() -> None:
    error = exception_for(
        status_code=401,
        body=problem(code=40102, detail="Token eyJhbGciOiJIUzI1NiJ9abcdefghij is invalid"),
        content_type="application/json",
    )
    assert "eyJhbGciOiJIUzI1NiJ9abcdefghij" not in str(error)
    assert "[REDACTED]" in str(error)


def test_repr_is_safe_and_terse() -> None:
    error = exception_for(
        status_code=403, body=problem(code=40303, title="Unauthorized_AccessData")
    )
    assert repr(error) == (
        "DataAccessError(http_status=403, code=40303, title='Unauthorized_AccessData')"
    )
