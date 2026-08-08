"""The Nmbrs facade: credentials, consent, tokens, and the way in to resources."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from nmbrs_rest import Company, Debtor, Employee, Nmbrs
from nmbrs_rest.client import EPOCH
from nmbrs_rest.errors import NmbrsConfigError, NotAuthenticatedError, ResourceNotFoundError
from nmbrs_rest.tokens import Token
from tests.helpers import SUBSCRIPTION_KEY

CLIENT_ID = "client-id"
CLIENT_SECRET = "client-secret"
REDIRECT = "https://app.example/callback"


def envelope(rows: list[dict[str, Any]], **pagination: Any) -> httpx.Response:
    body: dict[str, Any] = {"data": rows}
    if pagination:
        body["pagination"] = pagination
    return httpx.Response(200, json=body)


def token_response(access: str = "fresh", refresh: str = "rotated") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "company.info.read employee.info.read offline_access",
        },
    )


def build(
    handler: Any = None,
    identity: Any = None,
    **kwargs: Any,
) -> Nmbrs:
    """A Nmbrs wired to in-process fake API and identity servers."""
    api = Nmbrs(
        CLIENT_ID,
        CLIENT_SECRET,
        SUBSCRIPTION_KEY,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)) if handler else None,
        **kwargs,
    )
    if identity is not None:
        api._oauth._client = httpx.Client(transport=httpx.MockTransport(identity))
    return api


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #


def test_subscription_key_is_required() -> None:
    with pytest.raises(NmbrsConfigError, match="subscription_key is required"):
        Nmbrs(CLIENT_ID, CLIENT_SECRET, "")


def test_a_fresh_client_is_not_authenticated() -> None:
    api = Nmbrs(CLIENT_ID, CLIENT_SECRET, SUBSCRIPTION_KEY)
    assert not api.authenticated
    assert api.access_token is None
    assert api.refresh_token is None
    assert api.scopes == frozenset()


def test_reading_before_authenticating_says_what_to_do() -> None:
    api = Nmbrs(CLIENT_ID, CLIENT_SECRET, SUBSCRIPTION_KEY)
    with pytest.raises(NotAuthenticatedError) as caught:
        api.companies()
    message = str(caught.value)
    assert "api.login" in message
    assert "refresh_token=" in message


# --------------------------------------------------------------------------- #
# The authorization code flow
# --------------------------------------------------------------------------- #


def test_login_returns_a_url_and_remembers_the_state() -> None:
    api = Nmbrs(CLIENT_ID, CLIENT_SECRET, SUBSCRIPTION_KEY)
    url = api.login(REDIRECT, ["offline_access", "company.info.read"])

    assert url.startswith("https://identityservice.nmbrs.com/connect/authorize?")
    assert "offline_access" in url
    assert api.pending_login is not None
    assert api.pending_login.state in url


def test_login_defaults_include_offline_access() -> None:
    """Without it no refresh token is issued and the integration dies in an hour."""
    api = Nmbrs(CLIENT_ID, CLIENT_SECRET, SUBSCRIPTION_KEY)
    assert "offline_access" in api.login(REDIRECT)


def test_authenticate_exchanges_the_code_and_exposes_the_tokens() -> None:
    api = build(identity=lambda _r: token_response("at-1", "rt-1"))
    api.login(REDIRECT)
    assert api.pending_login is not None

    token = api.authenticate("the-code", state=api.pending_login.state)

    assert isinstance(token, Token)
    assert api.authenticated
    assert api.access_token == "at-1"
    assert api.refresh_token == "rt-1"
    assert "company.info.read" in api.scopes
    assert api.pending_login is None


def test_a_mismatched_state_is_refused_before_any_network_call() -> None:
    calls: list[str] = []

    def identity(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return token_response()

    api = build(identity=identity)
    api.login(REDIRECT)

    with pytest.raises(NmbrsConfigError, match="state mismatch"):
        api.authenticate("the-code", state="not-the-issued-state")
    assert calls == []


def test_pkce_verifier_is_carried_through_login_to_authenticate() -> None:
    sent: dict[str, str] = {}

    def identity(request: httpx.Request) -> httpx.Response:
        sent.update(dict(httpx.QueryParams(request.content.decode())))
        return token_response()

    api = build(identity=identity)
    url = api.login(REDIRECT, pkce=True)
    assert "code_challenge_method=S256" in url
    assert api.pending_login is not None
    verifier = api.pending_login.code_verifier

    api.authenticate("the-code", state=api.pending_login.state)
    assert sent["code_verifier"] == verifier


# --------------------------------------------------------------------------- #
# Tokens over time
# --------------------------------------------------------------------------- #


def test_access_token_is_live_not_a_snapshot() -> None:
    """The whole point of a property: a background refresh must be visible."""
    api = build(identity=lambda _r: token_response("second", "rt-2"))
    api._store.save("default", Token(access_token="first", refresh_token="rt-1", expires_at=EPOCH))
    assert api.access_token == "first"

    api.refresh()

    assert api.access_token == "second"
    assert api.refresh_token == "rt-2"


def test_on_token_refresh_is_told_about_rotation() -> None:
    seen: list[Token] = []
    api = build(
        identity=lambda _r: token_response("second", "rt-2"),
        on_token_refresh=seen.append,
    )
    api._store.save("default", Token(access_token="first", refresh_token="rt-1", expires_at=EPOCH))
    seen.clear()

    api.refresh()

    assert [t.refresh_token for t in seen] == ["rt-2"]


def test_a_failing_persistence_callback_still_leaves_the_client_usable() -> None:
    """Loud, but not destructive: the new token survives in memory."""

    def explode(_token: Token) -> None:
        raise RuntimeError("database is down")

    api = build(identity=lambda _r: token_response("second", "rt-2"), on_token_refresh=explode)
    api._memory.save("default", Token(access_token="first", refresh_token="rt-1", expires_at=EPOCH))

    with pytest.raises(RuntimeError, match="database is down"):
        api.refresh()

    assert api.access_token == "second"
    assert api.refresh_token == "rt-2"


def test_refreshing_without_a_refresh_token_explains_offline_access() -> None:
    api = Nmbrs(CLIENT_ID, CLIENT_SECRET, SUBSCRIPTION_KEY, access_token="only-access")
    with pytest.raises(NotAuthenticatedError, match="offline_access"):
        api.refresh()


def test_resuming_from_a_saved_refresh_token_refreshes_on_first_use() -> None:
    """No browser round trip when you already have a refresh token."""
    api_calls: list[str] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        api_calls.append(request.headers["authorization"])
        return envelope([{"companyId": "c-1", "name": "Acme"}])

    api = build(
        handler=api_handler,
        identity=lambda _r: token_response("minted", "rt-2"),
        refresh_token="saved-refresh-token",
    )
    assert api.authenticated

    companies = api.companies()

    assert api_calls == ["Bearer minted"]
    assert [c.name for c in companies] == ["Acme"]


def test_logout_revokes_upstream_and_forgets_everything() -> None:
    revoked: list[dict[str, str]] = []

    def identity(request: httpx.Request) -> httpx.Response:
        revoked.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={})

    api = build(identity=identity, access_token="at-1", refresh_token="rt-1")
    api.logout()

    assert revoked and revoked[0]["token"] == "rt-1"
    assert not api.authenticated
    assert api.access_token is None


# --------------------------------------------------------------------------- #
# Resources
# --------------------------------------------------------------------------- #


def test_companies_returns_objects_and_fetches_every_page() -> None:
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(dict(request.url.params).get("pageNumber", 1))
        pages.append(page)
        return envelope(
            [{"companyId": f"c-{page}", "name": f"Company {page}", "number": page}],
            currentPage=page,
            totalPages=3,
            totalRecords=3,
        )

    api = build(handler=handler, access_token="at-1")
    companies = api.companies()

    assert pages == [1, 2, 3]
    assert [type(c) for c in companies] == [Company, Company, Company]
    assert [c.id for c in companies] == ["c-1", "c-2", "c-3"]
    assert companies[0].name == "Company 1"
    assert companies[0].number == 1


def test_debtors_returns_objects() -> None:
    api = build(
        handler=lambda _r: envelope([{"debtorId": "d-1", "name": "Debtor One", "number": 7}]),
        access_token="at-1",
    )
    debtors = api.debtors()
    assert [type(d) for d in debtors] == [Debtor]
    assert debtors[0].id == "d-1"
    assert debtors[0].name == "Debtor One"


def test_the_same_company_id_yields_the_same_object() -> None:
    """Caching lives on the resource, so handing back a new object would discard it."""
    api = build(handler=lambda _r: envelope([]), access_token="at-1")
    assert api.company("c-1") is api.company("c-1")


def test_employees_are_built_from_the_listing_so_names_are_free() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return envelope(
            [
                {
                    "employeeId": "e-1",
                    "employeeBasicInfo": {
                        "employeeNumber": 42,
                        "firstName": "Ada",
                        "prefix": "van",
                        "lastName": "Lovelace",
                        "employeeType": "Payroll",
                    },
                }
            ]
        )

    api = build(handler=handler, access_token="at-1")
    employees = api.employees("c-1")

    assert [type(e) for e in employees] == [Employee]
    employee = employees[0]
    assert employee.id == "e-1"
    assert employee.company_id == "c-1"
    assert employee.full_name == "Ada van Lovelace"
    assert employee.employee_number == 42
    assert len(requests) == 1, "reading names must not cost extra requests"


def test_employee_by_id_filters_server_side_in_one_request() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return envelope([{"employeeId": "e-9", "employeeBasicInfo": {"firstName": "Grace"}}])

    api = build(handler=handler, access_token="at-1")
    employee = api.employee("c-1", "e-9")

    assert employee.first_name == "Grace"
    assert len(seen) == 1
    assert seen[0]["employeeId"] == "e-9", "must not page the whole company"


def test_an_employee_from_the_wrong_company_says_so() -> None:
    api = build(handler=lambda _r: envelope([]), access_token="at-1")
    with pytest.raises(ResourceNotFoundError, match="is not in company"):
        api.employee("c-1", "e-does-not-exist")
