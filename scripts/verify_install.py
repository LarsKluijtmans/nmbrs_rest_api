#!/usr/bin/env python3
"""Verify an *installed* ``nmbrs-rest-api`` behaves correctly.

This deliberately imports nothing from the source tree. Run it against a wheel
installed from TestPyPI (or anywhere else) and it exercises the package the way a
downstream user would::

    python scripts/verify_install.py

``scripts/try_testpypi.py`` runs this for you inside a throwaway virtualenv; use
this file directly when you already have the package installed somewhere.

Only ``httpx`` is used beyond the SDK itself, and that is a hard dependency of the
package, so this needs no dev extras. Network access is never required: the HTTP
layer is exercised through ``httpx.MockTransport``.
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

DIST_NAME = "nmbrs-rest-api"
IMPORT_NAME = "nmbrs_rest"

_CHECKS: list[tuple[str, Callable[[], str]]] = []


def check(title: str) -> Callable[[Callable[[], str]], Callable[[], str]]:
    def register(fn: Callable[[], str]) -> Callable[[], str]:
        _CHECKS.append((title, fn))
        return fn

    return register


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


def _token(access: str = "access-token-value") -> Any:
    from nmbrs_rest import Token

    return Token(
        access_token=access,
        refresh_token="refresh-token-value",
        expires_at=_future(),
        scopes=("company.info.read", "employee.employment.read"),
    )


def _transport(handler: Callable[[httpx.Request], httpx.Response]) -> Any:
    """A Transport wired to an in-process fake server."""
    from nmbrs_rest import Transport

    return Transport(
        subscription_key="subscription-key-value",
        token=_token(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _envelope(items: list[dict[str, Any]], **pagination: Any) -> httpx.Response:
    body: dict[str, Any] = {"data": items}
    if pagination:
        body["pagination"] = pagination
    return httpx.Response(200, json=body)


# --------------------------------------------------------------------------- #
# Packaging: is the artifact itself assembled correctly?
# --------------------------------------------------------------------------- #


@check("package imports and reports its version")
def _version() -> str:
    from importlib.metadata import version

    import nmbrs_rest

    installed = version(DIST_NAME)
    if nmbrs_rest.__version__ != installed:
        raise AssertionError(
            f"__version__ is {nmbrs_rest.__version__!r} but the installed "
            f"distribution is {installed!r} - the dist/import name mapping is wrong"
        )
    return f"{IMPORT_NAME} {installed}"


@check("running against the installed package, not a source tree")
def _not_source() -> str:
    import nmbrs_rest

    location = Path(nmbrs_rest.__file__ or "").resolve()
    if (location.parent / ".." / ".." / "pyproject.toml").resolve().exists():
        raise AssertionError(
            f"imported from a source checkout ({location}); this verifies nothing "
            "about the published artifact"
        )
    return str(location.parent)


@check("py.typed ships, so downstream type checkers see the annotations")
def _py_typed() -> str:
    from importlib.resources import files

    marker = files(IMPORT_NAME) / "py.typed"
    if not marker.is_file():
        raise AssertionError("py.typed missing (PEP 561); annotations will be ignored")
    return "present"


@check("vendored OpenAPI spec ships as package data")
def _spec() -> str:
    from importlib.resources import files

    spec = files(IMPORT_NAME) / "_spec" / "nmbrs-openapi.yaml"
    if not spec.is_file():
        raise AssertionError("_spec/nmbrs-openapi.yaml missing; wheels drop data files silently")
    return f"{len(spec.read_bytes()):,} bytes"


@check("public API surface is importable")
def _surface() -> str:
    import nmbrs_rest

    missing = [name for name in nmbrs_rest.__all__ if not hasattr(nmbrs_rest, name)]
    if missing:
        raise AssertionError(f"__all__ advertises names that do not exist: {missing}")
    return f"{len(nmbrs_rest.__all__)} public names"


@check("generated scope table covers every operation")
def _scopes() -> str:
    from nmbrs_rest._scopes import KNOWN_SCOPES, REQUIRED_SCOPES

    if len(REQUIRED_SCOPES) != 123:
        raise AssertionError(
            f"expected 123 operations in the scope table, found {len(REQUIRED_SCOPES)}"
        )
    return f"{len(REQUIRED_SCOPES)} operations, {len(KNOWN_SCOPES)} scopes"


@check("generated read methods are present on the resource classes")
def _read_surface() -> str:
    from nmbrs_rest import Company, Debtor, Employee

    counts = {}
    for cls, expected in ((Employee, 34), (Company, 19), (Debtor, 7)):
        found = sum(
            1
            for name in dir(cls)
            if not name.startswith("_") and callable(getattr(cls, name, None))
        )
        if found < expected:
            raise AssertionError(f"{cls.__name__} exposes {found} reads, expected >= {expected}")
        counts[cls.__name__] = found
    return ", ".join(f"{k} {v}" for k, v in counts.items())


@check("the Nmbrs facade refuses to read before authenticating")
def _facade() -> str:
    from nmbrs_rest import Nmbrs
    from nmbrs_rest.errors import NotAuthenticatedError

    api = Nmbrs("client-id", "client-secret", "subscription-key-value")
    url = api.login("https://app.example/callback")
    if not url.startswith("https://identityservice.nmbrs.com/connect/authorize?"):
        raise AssertionError(f"login() built an unexpected URL: {url}")
    if "offline_access" not in url:
        raise AssertionError("default scopes omit offline_access, so no refresh token")

    try:
        api.companies()
    except NotAuthenticatedError:
        return "login() builds a consent URL; reads raise until authenticated"
    raise AssertionError("reading without a token should have raised NotAuthenticatedError")


# --------------------------------------------------------------------------- #
# Behaviour: does the thing actually work?
# --------------------------------------------------------------------------- #


@check("a 403 names the exact scope that is missing")
def _scope_diagnosis() -> str:
    from nmbrs_rest import InsufficientScopeError
    from nmbrs_rest.errors import Operation, exception_for

    error = exception_for(
        status_code=403,
        body=json.dumps({"code": 40303, "type": "authenticationError"}).encode(),
        content_type="application/json",
        operation=Operation(
            method="GET",
            template="/api/companies/{companyId}/employees/salaries",
            granted_scopes=frozenset({"company.info.read"}),
        ),
    )
    if not isinstance(error, InsufficientScopeError):
        raise AssertionError(f"expected InsufficientScopeError, got {type(error).__name__}")
    if "employee.employment.read" not in str(error):
        raise AssertionError(f"message does not name the missing scope: {error}")
    return "employee.employment.read"


@check("error messages never leak a token")
def _redaction() -> str:
    from nmbrs_rest.errors import exception_for

    secret = "eyJhbGciOiJIUzI1NiJ9abcdefghijklmnop"
    error = exception_for(
        status_code=401,
        body=json.dumps({"code": 40102, "detail": f"Token {secret} is invalid"}).encode(),
        content_type="application/json",
    )
    if secret in str(error):
        raise AssertionError("access token leaked into the exception message")
    if "[REDACTED]" not in str(error):
        raise AssertionError(f"expected redaction marker in: {error}")
    return "redacted"


@check("Token repr hides the secrets")
def _token_repr() -> str:
    token = _token()
    rendered = f"{token!r} {token}"
    for secret in ("access-token-value", "refresh-token-value"):
        if secret in rendered:
            raise AssertionError(f"{secret!r} leaked into repr/str: {rendered}")
    return "safe"


@check("FileTokenStore round-trips a token")
def _file_store() -> str:
    from nmbrs_rest import FileTokenStore

    with tempfile.TemporaryDirectory() as tmp:
        store = FileTokenStore(Path(tmp) / "tokens.json")
        original = _token()
        store.save("default", original)
        loaded = store.load("default")

    if loaded is None:
        raise AssertionError("token did not survive a save/load round trip")
    if loaded.access_token != original.access_token:
        raise AssertionError("access token changed across the round trip")
    if loaded.refresh_token != original.refresh_token:
        raise AssertionError("refresh token changed across the round trip")
    return "round-tripped"


@check("requests carry both mandatory auth headers")
def _headers() -> str:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return _envelope([{"companyId": "c-1", "name": "Acme"}])

    transport = _transport(handler)
    transport.get_json("/api/companies")

    if seen.get("authorization") != "Bearer access-token-value":
        raise AssertionError(f"Authorization header wrong: {seen.get('authorization')!r}")
    if seen.get("x-subscription-key") != "subscription-key-value":
        raise AssertionError(
            f"X-Subscription-Key header missing: {seen.get('x-subscription-key')!r}"
        )
    return "Authorization + X-Subscription-Key"


@check("the {data, pagination} envelope is unwrapped")
def _unwrap() -> str:
    from nmbrs_rest.pagination import unwrap_one

    def handler(_: httpx.Request) -> httpx.Response:
        return _envelope([{"companyId": "c-1", "name": "Acme"}])

    payload = _transport(handler).get_json("/api/companies/{companyId}", path="/api/companies/c-1")
    item = unwrap_one(payload, template="/api/companies/{companyId}")
    if item["name"] != "Acme":
        raise AssertionError(f"unwrapped the wrong thing: {item}")
    return "single read unwrapped from the list envelope"


@check("pages are followed automatically and lazily")
def _pagination() -> str:
    from nmbrs_rest.pagination import Page

    requested: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(dict(request.url.params).get("pageNumber", 1))
        requested.append(page)
        return _envelope(
            [{"id": f"e-{(page - 1) * 2 + n}"} for n in (1, 2)],
            currentPage=page,
            totalPages=3,
            totalRecords=6,
        )

    page: Any = Page(
        _transport(handler),
        "/api/companies/{companyId}/employees",
        path="/api/companies/c-1/employees",
        factory=lambda row: row["id"],
    )

    if requested:
        raise AssertionError("Page fetched before anyone iterated it; it is meant to be lazy")

    items = list(page)
    if items != ["e-1", "e-2", "e-3", "e-4", "e-5", "e-6"]:
        raise AssertionError(f"pagination produced {items}")
    if requested != [1, 2, 3]:
        raise AssertionError(f"expected pages 1..3 to be fetched once each, got {requested}")
    return "3 pages, 6 records, nothing fetched until iteration"


@check("a 401 triggers exactly one refresh and replays the request")
def _refresh_on_401() -> str:
    from nmbrs_rest import MemoryTokenStore, Token, Transport

    calls: list[str] = []

    def api(request: httpx.Request) -> httpx.Response:
        auth = request.headers["authorization"]
        calls.append(auth)
        if auth == "Bearer stale":
            return httpx.Response(
                401,
                json={"code": 40102, "type": "authenticationError", "title": "Unauthorized"},
                headers={"Content-Type": "application/json"},
            )
        return _envelope([{"companyId": "c-1"}])

    def identity(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "fresh",
                "refresh_token": "rotated",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    from nmbrs_rest import OAuth

    oauth = OAuth(
        client_id="client-id",
        client_secret="client-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(identity)),
    )
    store = MemoryTokenStore()
    stale = Token(
        access_token="stale",
        refresh_token="refresh-token-value",
        expires_at=_future(),  # not expired by our clock; the server rejects it anyway
    )
    store.save("default", stale)

    transport = Transport(
        subscription_key="subscription-key-value",
        oauth=oauth,
        token_store=store,
        http_client=httpx.Client(transport=httpx.MockTransport(api)),
    )
    transport.get_json("/api/companies")

    if calls != ["Bearer stale", "Bearer fresh"]:
        raise AssertionError(f"expected one refresh and one replay, saw {calls}")
    stored = store.load("default")
    if stored is None or stored.refresh_token != "rotated":
        raise AssertionError("the rotated refresh token was not persisted")
    return "refreshed, replayed, rotation persisted"


# --------------------------------------------------------------------------- #


def main() -> int:
    print(f"verifying installed {DIST_NAME}\n")
    failures = 0
    width = max(len(title) for title, _ in _CHECKS)

    for title, fn in _CHECKS:
        try:
            detail = fn()
        except Exception as exc:
            failures += 1
            print(f"FAIL  {title.ljust(width)}  {type(exc).__name__}: {exc}")
            traceback.print_exc(file=sys.stdout)
        else:
            print(f"ok    {title.ljust(width)}  {detail}")

    total = len(_CHECKS)
    print()
    if failures:
        print(f"{failures} of {total} checks FAILED")
        return 1
    print(f"all {total} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
