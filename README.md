# nmbrs-rest-api

Python SDK for the [Nmbrs](https://www.nmbrs.com/) public REST API, with lazy-loading
debtor, company and employee objects.

[![PyPI](https://img.shields.io/pypi/v/nmbrs-rest-api.svg)](https://pypi.org/project/nmbrs-rest-api/)
[![Python versions](https://img.shields.io/pypi/pyversions/nmbrs-rest-api.svg)](https://pypi.org/project/nmbrs-rest-api/)
[![License](https://img.shields.io/pypi/l/nmbrs-rest-api.svg)](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/LICENSE)
[![CI](https://github.com/LarsKluijtmans/nmbrs_rest_api/actions/workflows/ci.yml/badge.svg)](https://github.com/LarsKluijtmans/nmbrs_rest_api/actions/workflows/ci.yml)

> **Status: design stage.** The architecture, authentication contract and error model are
> written up and reviewed, but the client is not implemented yet. Installing the package
> today gets you a version number and nothing else. The code below is the intended API,
> not a description of shipped behaviour. Watch the repo for the first usable release.

## Install

```bash
pip install nmbrs-rest-api
```

The distribution is `nmbrs-rest-api`; the import name is `nmbrs_rest`. See
[Relationship to the SOAP SDK](#relationship-to-the-soap-sdk) for why they differ.

## The idea

Nmbrs' REST API is company-scoped: almost everything about an employee is only readable
through a company-wide endpoint, and the single-employee endpoint doesn't even tell you
which company an employee belongs to. That makes straightforward code annoying to write.

This SDK hides that. You ask for an employee and read attributes; it works out which
requests to make, when, and caches them.

```python
from nmbrs_rest import Nmbrs

api = Nmbrs(
    subscription_key="...",
    access_token="...",
    refresh_token="...",
    client_id="...",
    client_secret="...",
    on_token_refresh=save_tokens,   # refresh tokens rotate - persist them
)

employee = api.employee("ecbf546b-5c94-4eec-8557-32f5b65d30e2")

employee.personal_info        # GET /api/employees/{id}
employee.contracts            # resolves the company, then fetches + caches
employee.salaries             # cached company context, one request
employee.leave_requests(year=2026)
```

Nothing is fetched until you touch it, and nothing is fetched twice.

Company-first works too, and skips the company lookup entirely:

```python
company = api.company("ad3562fc-b050-4de7-9eb0-1751eefa680c")

for employee in company.employees():      # auto-paginating
    print(employee.personal_info.first_name)

employee = company.employee("ecbf546b-...")
```

## Features

- **Lazy loading** — attribute access triggers the request; results are cached per object.
- **Automatic pagination** — iterate a collection, the SDK walks the pages.
- **Company resolution** — `api.employee(id)` works standalone, resolving and caching the
  owning company in memory when it first needs it.
- **OAuth 2.0 handled** — authorization code flow, PAR, and automatic token refresh with a
  pluggable `TokenStore`.
- **Meaningful errors** — a 403 tells you *which scope* is missing for *which operation*,
  not just "Forbidden".
- **Typed** — ships `py.typed`; models generated from the official OpenAPI spec.

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
