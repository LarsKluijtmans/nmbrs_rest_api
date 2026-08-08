# nmbrs-rest-api

Python SDK for the [Nmbrs](https://www.nmbrs.com/) public REST API, with cached
debtor, company and employee objects.

[![PyPI](https://img.shields.io/pypi/v/nmbrs-rest-api.svg)](https://pypi.org/project/nmbrs-rest-api/)
[![Python versions](https://img.shields.io/pypi/pyversions/nmbrs-rest-api.svg)](https://pypi.org/project/nmbrs-rest-api/)
[![License](https://img.shields.io/pypi/l/nmbrs-rest-api.svg)](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/LICENSE)
[![CI](https://github.com/LarsKluijtmans/nmbrs_rest_api/actions/workflows/ci.yml/badge.svg)](https://github.com/LarsKluijtmans/nmbrs_rest_api/actions/workflows/ci.yml)

> **Status: usable, pre-1.0.** Every read endpoint is implemented and tested; writes are
> not (see [Scope](#scope)). Responses come back as plain dicts for now — typed models
> are the next step. The API may still change before 1.0.

## Install

```bash
pip install nmbrs-rest-api
```

The distribution is `nmbrs-rest-api`; the import name is `nmbrs_rest`. See
[Relationship to the SOAP SDK](#relationship-to-the-soap-sdk) for why they differ.

## Quickstart

```python
from nmbrs_rest import Nmbrs

api = Nmbrs(client_id, client_secret, subscription_key)

# 1. Send the user here to approve. Nmbrs supports only the authorization code
#    flow, so this step needs a human exactly once.
url = api.login("https://yourapp.example/callback")

# 2. Hand back the code from the redirect.
api.authenticate(code)

# 3. Persist these. The refresh token is good for 30 days.
api.access_token
api.refresh_token
```

Next time, skip the browser entirely:

```python
api = Nmbrs(client_id, client_secret, subscription_key, refresh_token=saved)
```

Then read:

```python
for company in api.companies():
    print(company.name)

    for employee in api.employees(company.id):
        print(employee.full_name)              # free, came with the listing

        employee.contracts()                   # one request, then cached
        employee.salaries()
        employee.fixed_hours(year=2026, period=3)
```

Or go straight to one employee, in a single request:

```python
employee = api.employee(company_id, employee_id)
```

## What this hides

Nmbrs' REST API is company-scoped and inconsistent in ways that leak into every
integration written against it. The SDK absorbs that:

**Employee data is only readable through the owning company.** There is no
employee-to-company lookup, so both ids are always required — `api.employee(company_id,
employee_id)`. Nothing scans, nothing is unexpectedly slow.

**Responses are wrapped twice.** Everything arrives as `{"data": [...]}`, even a single
record, and employee reads are wrapped again as `{"employeeId": ..., "contracts": [...]}`
— with a payload key that differs per endpoint (`contracts`, `info`,
`EmployeeLeaveRequests`). You get the payload.

**Three endpoints ignore `employeeId`.** `privateInfos`, `extraFields` and
`useraccounts` return the whole company whatever you ask for. The SDK filters them
client-side so `employee.private_info()` means what it says.

**Paging is manual.** Every list read follows pages until they run out.

**Reads take filters, so they are methods.** 33 of the 38 employee endpoints accept
`year`, `period` or `created_from`, which an attribute cannot express. Results are cached
per argument set, so `employee.contracts()` twice is one request but
`employee.contracts(created_from=...)` is its own question:

```python
employee.contracts()                          # request
employee.contracts()                          # cached
employee.contracts(created_from=date(2026, 1, 1))   # request
employee.refresh()                            # drop this object's cache
```

**403s name the scope you are missing.** The spec declares required scopes per
operation, so the SDK can tell you which one to re-consent with:

```
InsufficientScopeError: [403/40303] GET /api/companies/ad3562fc/employees/salaries: no detail provided

  This operation accepts any of:  employee.employment, employee.employment.read
  Your token was granted:         company.info.read, employee.info.read

  Scope is fixed at consent time and cannot be widened for an existing
  token. Re-run the authorization flow including one of the scopes above.
```

## Refresh tokens rotate

Nmbrs invalidates the old refresh token every time it issues a new one. `api.access_token`
and `api.refresh_token` are live properties rather than snapshots, so they always reflect
the latest values — but if your app persists them, ask to be told instead of polling:

```python
def save(token):
    db.store(token.access_token, token.refresh_token, token.expires_at)

api = Nmbrs(client_id, client_secret, subscription_key,
            refresh_token=saved, on_token_refresh=save)
```

Persisting a stale refresh token is the single most common way a Nmbrs integration dies
overnight. See [docs/authentication.md](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/docs/authentication.md).

## Web apps

`login()` remembers the CSRF `state`, the PKCE verifier and the redirect URI on the
client object, which is all a script needs. A web app usually handles the redirect in a
different request or worker, so pass them back explicitly:

```python
url = api.login(redirect_uri, scopes, pkce=True)
session["state"] = api.pending_login.state
session["verifier"] = api.pending_login.code_verifier

# ... later, in the callback handler ...
api.authenticate(code, state=session["state"], code_verifier=session["verifier"])
```

## Scope

Reads only. All 84 GET operations are implemented: 34 employee reads, 19 company reads,
7 debtor reads, plus the listings. The 39 write operations are not — they are planned for
a later release.

The read methods are generated from the vendored OpenAPI spec, and CI fails if they drift
from it.

## Features

- **Automatic pagination** — every list read follows pages until they run out.
- **Per-object caching** — keyed on the filter arguments, so the same question is asked
  once and a different question is not served a stale answer.
- **OAuth 2.0 handled end to end** — `login()`, `authenticate()`, refresh-on-401 with
  replay, and rotation persisted before use.
- **Meaningful errors** — a 403 tells you *which scope* is missing for *which operation*,
  not just "Forbidden".
- **Typed** — ships `py.typed`; read methods generated from the official OpenAPI spec,
  with CI failing if they drift from it.

## Documentation

- [Design](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/DESIGN.md) — architecture and the full API surface
- [Authentication](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/docs/authentication.md) — OAuth flow, and how to save and keep tokens
- [Errors](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/docs/errors.md) — every error code and what to do about it
- [Releasing](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/docs/releasing.md) — publishing to TestPyPI and PyPI
- [Contributing](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/CONTRIBUTING.md)

Upstream API reference: [Nmbrs Public REST API](https://nmbrs.stoplight.io/docs/nmbrs-restapi).

## Requirements

- Python 3.10+
- Nmbrs OAuth credentials and a subscription key from the
  [Nmbrs Developer Portal](https://developer.nmbrs.com/)

Nmbrs offers no sandbox. Development and testing need a Nmbrs demo environment, which does
not expire.

## Relationship to the SOAP SDK

Nmbrs has two APIs, and this project covers one of them:

| | Package | Import | Covers |
|---|---|---|---|
| SOAP | [`nmbrs`](https://pypi.org/project/nmbrs/) ([repo](https://github.com/LarsKluijtmans/nmbrs_api)) | `nmbrs` | The legacy SOAP API, retiring **2027-03-01** |
| REST | `nmbrs-rest-api` (this one) | `nmbrs_rest` | The current REST API |

Both are by the same author. The import names differ deliberately so the two can be
installed side by side while you migrate:

```python
import nmbrs        # SOAP
import nmbrs_rest   # REST
```

The REST API does not yet cover everything SOAP does, so a period of running both is
expected rather than exceptional.

## A note on upstream stability

The Nmbrs REST API is **unversioned** — no version in the URL, header or query string.
Nmbrs ships additive changes without notice. Models therefore tolerate unknown fields
rather than rejecting them, so a new field appearing upstream will not break your code.

## License

[Apache-2.0](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/LICENSE)

This is an independent, unofficial SDK. It is not affiliated with or endorsed by Nmbrs or
Visma.
