"""Transport: headers, refresh-on-401, retry policy, error mapping."""

from __future__ import annotations

import httpx
import pytest
import respx

from nmbrs_rest.auth import TOKEN_URL, OAuth
from nmbrs_rest.errors import (
    DataAccessError,
    InsufficientScopeError,
    NmbrsConfigError,
    NmbrsTimeoutError,
    QuotaExceededError,
    RateLimitError,
    ReauthorizationRequired,
    ServerError,
    ValidationError,
)
from nmbrs_rest.tokens import MemoryTokenStore, Token
from nmbrs_rest.transport import DEFAULT_BASE_URL, Transport
from tests.helpers import SUBSCRIPTION_KEY, make_token

COMPANIES = f"{DEFAULT_BASE_URL}/api/companies"
TEMPLATE = "/api/companies"


def build(token: Token | None = None, **kwargs: object) -> Transport:
    return Transport(
        subscription_key=SUBSCRIPTION_KEY,
        token=token or make_token(),
        **kwargs,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


def test_subscription_key_is_required_and_says_why() -> None:
    with pytest.raises(NmbrsConfigError, match="X-Subscription-Key"):
        Transport(subscription_key="", token=make_token())


def test_a_token_is_required() -> None:
    with pytest.raises(NmbrsConfigError, match="no token available"):
        Transport(subscription_key=SUBSCRIPTION_KEY)


def test_a_prepopulated_store_is_enough() -> None:
    store = MemoryTokenStore()
    store.save("acme", make_token())
    transport = Transport(subscription_key=SUBSCRIPTION_KEY, token_store=store, token_key="acme")
    assert transport.token.access_token == "access-aaa"


# --------------------------------------------------------------------------- #
# Headers
# --------------------------------------------------------------------------- #


@respx.mock
def test_both_mandatory_headers_are_sent() -> None:
    route = respx.get(COMPANIES).mock(return_value=httpx.Response(200, json={"data": []}))
    build().request("GET", TEMPLATE)

    headers = route.calls[0].request.headers
    assert headers["Authorization"] == "Bearer access-aaa"
    assert headers["X-Subscription-Key"] == SUBSCRIPTION_KEY
    assert headers["User-Agent"].startswith("nmbrs-rest-api/")


@respx.mock
def test_none_params_are_dropped() -> None:
    route = respx.get(COMPANIES).mock(return_value=httpx.Response(200, json={"data": []}))
    build().request("GET", TEMPLATE, params={"year": 2026, "period": None})

    query = route.calls[0].request.url.params
    assert query["year"] == "2026"
    assert "period" not in query


# --------------------------------------------------------------------------- #
# Refresh
# --------------------------------------------------------------------------- #


@respx.mock
def test_expired_token_refreshes_before_the_request() -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "fresh", "refresh_token": "rt2", "expires_in": 3600}
        )
    )
    route = respx.get(COMPANIES).mock(return_value=httpx.Response(200, json={"data": []}))

    store = MemoryTokenStore()
    transport = Transport(
        subscription_key=SUBSCRIPTION_KEY,
        token=make_token(expires_in=-10),
        oauth=OAuth("id", "secret", "https://app/cb"),
        token_store=store,
    )
    transport.request("GET", TEMPLATE)

    assert route.calls[0].request.headers["Authorization"] == "Bearer fresh"
    stored = store.load("default")
    assert stored is not None
    # Persisted BEFORE use - this is the rule that prevents lockout.
    assert stored.access_token == "fresh"
    assert stored.refresh_token == "rt2"


@respx.mock
def test_a_401_triggers_exactly_one_refresh_and_replay() -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "fresh", "refresh_token": "rt2", "expires_in": 3600}
        )
    )
    route = respx.get(COMPANIES).mock(
        side_effect=[
            httpx.Response(401, json={"code": 40102, "type": "authenticationError"}),
            httpx.Response(200, json={"data": [{"companyId": "c1"}]}),
        ]
    )
    transport = build(oauth=OAuth("id", "secret", "https://app/cb"))
    response = transport.request("GET", TEMPLATE)

    assert response.status_code == 200
    assert route.call_count == 2
    assert route.calls[1].request.headers["Authorization"] == "Bearer fresh"


@respx.mock
def test_a_second_401_is_not_retried_forever() -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})
    )
    route = respx.get(COMPANIES).mock(
        return_value=httpx.Response(401, json={"code": 40102, "type": "authenticationError"})
    )
    with pytest.raises(Exception, match=r"40102|Invalid"):
        build(oauth=OAuth("id", "secret", "https://app/cb")).request("GET", TEMPLATE)
    assert route.call_count == 2  # original + one replay, then give up


@respx.mock
def test_dead_refresh_token_becomes_reauthorization_required() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    respx.get(COMPANIES).mock(return_value=httpx.Response(200, json={"data": []}))

    transport = Transport(
        subscription_key=SUBSCRIPTION_KEY,
        token=make_token(expires_in=-10),
        oauth=OAuth("id", "secret", "https://app/cb"),
        token_key="acme",
    )
    with pytest.raises(ReauthorizationRequired) as exc_info:
        transport.request("GET", TEMPLATE)
    assert exc_info.value.token_key == "acme"


@respx.mock
def test_a_refresh_race_reuses_the_winners_token() -> None:
    """invalid_grant WITH a newer token in the store is benign, not terminal."""
    store = MemoryTokenStore()
    store.save("default", make_token(expires_in=-10, refresh_token="rt-old"))

    def _rotated_by_another_worker(request: httpx.Request) -> httpx.Response:
        store.save("default", make_token(access_token="winner", refresh_token="rt-new"))
        return httpx.Response(400, json={"error": "invalid_grant"})

    respx.post(TOKEN_URL).mock(side_effect=_rotated_by_another_worker)
    route = respx.get(COMPANIES).mock(return_value=httpx.Response(200, json={"data": []}))

    transport = Transport(
        subscription_key=SUBSCRIPTION_KEY,
        token_store=store,
        oauth=OAuth("id", "secret", "https://app/cb"),
    )
    transport.request("GET", TEMPLATE)
    assert route.calls[0].request.headers["Authorization"] == "Bearer winner"


def test_expired_token_without_oauth_is_actionable() -> None:
    transport = build(make_token(expires_in=-10))
    with pytest.raises(ReauthorizationRequired, match="no OAuth client"):
        transport.request("GET", TEMPLATE)


# --------------------------------------------------------------------------- #
# Retry policy
# --------------------------------------------------------------------------- #


@respx.mock
def test_throttling_is_retried() -> None:
    route = respx.get(COMPANIES).mock(
        side_effect=[
            httpx.Response(429, json={"code": 42908, "type": "throttlingError"}),
            httpx.Response(200, json={"data": []}),
        ]
    )
    build().request("GET", TEMPLATE)
    assert route.call_count == 2


@respx.mock
def test_quota_exceeded_is_never_retried() -> None:
    route = respx.get(COMPANIES).mock(
        return_value=httpx.Response(429, json={"code": 42909, "type": "throttlingError"})
    )
    with pytest.raises(QuotaExceededError):
        build().request("GET", TEMPLATE)
    assert route.call_count == 1


@respx.mock
def test_rate_limit_retries_are_bounded() -> None:
    route = respx.get(COMPANIES).mock(
        return_value=httpx.Response(429, json={"code": 42908, "type": "throttlingError"})
    )
    with pytest.raises(RateLimitError):
        build(max_rate_limit_retries=2).request("GET", TEMPLATE)
    assert route.call_count == 3  # initial + 2 retries


@respx.mock
def test_retry_after_is_honoured_when_present() -> None:
    respx.get(COMPANIES).mock(
        return_value=httpx.Response(
            429, json={"code": 42908, "type": "throttlingError"}, headers={"Retry-After": "7"}
        )
    )
    with pytest.raises(RateLimitError) as exc_info:
        build(max_rate_limit_retries=0).request("GET", TEMPLATE)
    assert exc_info.value.retry_after == 7.0


@respx.mock
def test_503_is_retried_but_500_is_not() -> None:
    unavailable = respx.get(COMPANIES).mock(
        side_effect=[
            httpx.Response(503, json={"code": 50301, "type": "apiError"}),
            httpx.Response(200, json={"data": []}),
        ]
    )
    build().request("GET", TEMPLATE)
    assert unavailable.call_count == 2

    respx.reset()
    internal = respx.get(COMPANIES).mock(
        return_value=httpx.Response(500, json={"code": 50001, "type": "apiError"})
    )
    with pytest.raises(ServerError):
        build().request("GET", TEMPLATE)
    assert internal.call_count == 1


@respx.mock
def test_client_errors_are_not_retried() -> None:
    route = respx.get(COMPANIES).mock(
        return_value=httpx.Response(400, json={"code": 40033, "type": "validationError"})
    )
    with pytest.raises(ValidationError):
        build().request("GET", TEMPLATE)
    assert route.call_count == 1


@respx.mock
def test_get_timeouts_are_retried() -> None:
    route = respx.get(COMPANIES).mock(
        side_effect=[httpx.TimeoutException("slow"), httpx.Response(200, json={"data": []})]
    )
    build().request("GET", TEMPLATE)
    assert route.call_count == 2


@respx.mock
def test_write_timeouts_are_not_retried() -> None:
    """A timed-out write may still have been applied upstream."""
    route = respx.post(COMPANIES).mock(side_effect=httpx.TimeoutException("slow"))
    with pytest.raises(NmbrsTimeoutError):
        build().request("POST", TEMPLATE, json={})
    assert route.call_count == 1


# --------------------------------------------------------------------------- #
# Error enrichment
# --------------------------------------------------------------------------- #


@respx.mock
def test_403_names_the_missing_scope() -> None:
    template = "/api/companies/{companyId}/employees/salaries"
    respx.get(f"{DEFAULT_BASE_URL}/api/companies/c1/employees/salaries").mock(
        return_value=httpx.Response(403, json={"code": 40303, "type": "authenticationError"})
    )
    transport = build(make_token(scopes=("company.info.read",)))

    with pytest.raises(InsufficientScopeError) as exc_info:
        transport.request("GET", template, path="/api/companies/c1/employees/salaries")

    assert exc_info.value.missing == frozenset({"employee.employment", "employee.employment.read"})


@respx.mock
def test_403_with_the_scope_present_points_at_data_access() -> None:
    template = "/api/companies/{companyId}/employees/salaries"
    respx.get(f"{DEFAULT_BASE_URL}/api/companies/c1/employees/salaries").mock(
        return_value=httpx.Response(403, json={"code": 40303, "type": "authenticationError"})
    )
    transport = build(make_token(scopes=("employee.employment.read",)))

    with pytest.raises(DataAccessError) as exc_info:
        transport.request("GET", template, path="/api/companies/c1/employees/salaries")
    assert "not a scope problem" in str(exc_info.value)


@respx.mock
def test_errors_carry_the_operation() -> None:
    respx.get(COMPANIES).mock(
        return_value=httpx.Response(400, json={"code": 40033, "type": "validationError"})
    )
    with pytest.raises(ValidationError) as exc_info:
        build().request("GET", TEMPLATE)
    assert exc_info.value.method == "GET"
    assert exc_info.value.path == TEMPLATE
