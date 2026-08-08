# nmbrs-rest-api

Python SDK for the [Nmbrs](https://www.nmbrs.com/) public REST API, with cached
debtor, company and employee objects.

[![PyPI](https://img.shields.io/pypi/v/nmbrs-rest-api.svg)](https://pypi.org/project/nmbrs-rest-api/)
[![Python versions](https://img.shields.io/pypi/pyversions/nmbrs-rest-api.svg)](https://pypi.org/project/nmbrs-rest-api/)
[![License](https://img.shields.io/pypi/l/nmbrs-rest-api.svg)](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/LICENSE)
[![CI](https://github.com/LarsKluijtmans/nmbrs_rest_api/actions/workflows/ci.yml/badge.svg)](https://github.com/LarsKluijtmans/nmbrs_rest_api/actions/workflows/ci.yml)

> **Status: usable, pre-1.0.** Every read endpoint is implemented and tested; writes are
> not. Responses come back as plain dicts for now — typed models are next. The API may
> still change before 1.0.

**[Install](#install)** · **[Quickstart](#quickstart)** · **[Authentication](#authentication)** ·
**[Reading data](#reading-data)** · **[Errors](#errors)** · **[Scopes](#scopes)** ·
**[Example project](#example-project)** · **[Reporting bugs](#reporting-bugs)**

## Install

```bash
pip install nmbrs-rest-api
```

The distribution is `nmbrs-rest-api`; the import name is `nmbrs_rest`. See
[Relationship to the SOAP SDK](#relationship-to-the-soap-sdk) for why they differ.

Python 3.10+. You will need OAuth credentials and a subscription key from the
[Nmbrs Developer Portal](https://developer.nmbrs.com/).

## Quickstart

```python
from nmbrs_rest import Nmbrs

api = Nmbrs(client_id, client_secret, subscription_key)

# 1. Send the user here to approve. Nmbrs supports only the authorization code
#    flow, so this needs a human — once.
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

for company in api.companies():
    for employee in api.employees(company.id):
        print(employee.full_name, employee.contracts())
```

There is a complete, runnable version of this in
**[`example/`](https://github.com/LarsKluijtmans/nmbrs_rest_api/tree/main/example)**.

## Authentication

Nmbrs offers the OAuth 2.0 authorization code flow and nothing else — no client
credentials, no API-key-only mode. The first token always requires a person to approve
in a browser.

### First run

```python
api = Nmbrs(
    client_id, client_secret, subscription_key,
    redirect_uri="http://localhost:4000",     # must be registered on your app
    on_token_refresh=save_tokens,             # see below
)

url = api.login(scopes=["offline_access", "company.info.read", "employee.info.read"])
# ... user approves, browser redirects to your redirect_uri with ?code=...
api.authenticate(code, state=state_from_the_redirect)
```

Include `offline_access` or **no refresh token is issued** and everything stops working
in an hour. The default scope set includes it.

### Refresh tokens rotate

Nmbrs invalidates the old refresh token every time it issues a new one. `access_token`
and `refresh_token` are live properties rather than snapshots, so they always reflect
the current values — but if your app persists them, ask to be told:

```python
def save_tokens(token):
    db.store(token.access_token, token.refresh_token, token.expires_at)

api = Nmbrs(client_id, client_secret, subscription_key,
            refresh_token=saved, on_token_refresh=save_tokens)
```

Persisting a stale refresh token is the single most common way a Nmbrs integration dies
overnight. The SDK refreshes before expiry, refreshes again if the server rejects a
token, replays the request, and persists the rotated token before using it.

### Web apps

`login()` remembers the CSRF `state`, the PKCE verifier and the redirect URI on the
client, which is all a script needs. A web app handles the redirect in a different
request, so pass them back:

```python
url = api.login(redirect_uri, scopes, pkce=True)
session["state"] = api.pending_login.state
session["verifier"] = api.pending_login.code_verifier

# ... later, in the callback handler ...
api.authenticate(code, state=session["state"], code_verifier=session["verifier"])
```

Also available: `api.refresh()` to force a refresh, `api.logout()` to revoke upstream
and clear local state, and `api.scopes` for what was actually granted (which can be
narrower than what you asked for).

Full contract: [docs/authentication.md](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/docs/authentication.md).

## Reading data

### Getting around

```python
api.debtors()                          # -> list[Debtor]
api.companies()                        # -> list[Company]
api.employees(company_id)              # -> list[Employee]
api.employee(company_id, employee_id)  # -> Employee, one request

api.company(company_id)                # -> Company, no request yet
api.debtor(debtor_id)                  # -> Debtor,  no request yet
```

Collections are eager — every page is fetched before the list comes back.

`api.company(id)` returns the **same object** each time, so its cache survives across
your own code.

**Both ids are required for an employee.** Nmbrs exposes no employee-to-company lookup,
so an employee id on its own cannot reach its own data.

### Reads are methods

33 of the 38 employee endpoints take a filter — `year`, `period`, `created_from` — which
an attribute cannot express. So every read is a method, and the parentheses mark where
I/O happens:

```python
employee = api.employee(company_id, employee_id)

employee.contracts()
employee.salaries()
employee.addresses()
employee.fixed_hours(year=2026, period=3)
employee.leave_requests(year=2026, status="Approved", request_type="Holiday")
employee.contracts(created_from=date(2020, 1, 1))    # pass real dates

employee.details()   # personalInfo, manager, department, function, address — 1 request
```

Identity fields come free with the company listing, so reading names costs nothing:

```python
employee.id, employee.company_id
employee.first_name, employee.last_name, employee.full_name
employee.employee_number, employee.employee_type
```

Company and debtor reads work the same way:

```python
company.period()                 # current payroll period
company.wage_taxes(year=2026)
company.cost_centers()
company.leave_groups()

debtor.companies()               # -> list[Company]
debtor.managers()
debtor.tags()
```

There are 60 generated read methods in total — 34 on `Employee`, 19 on `Company`, 7 on
`Debtor` — derived from the official OpenAPI spec, with CI failing if they drift from it.

### Caching

Per object, keyed on the **filter arguments**, not just the endpoint:

```python
employee.contracts()                              # request
employee.contracts()                              # cached
employee.contracts(created_from=date(2026, 1, 1)) # different question, own entry

employee.cached      # how many distinct reads are held
employee.refresh()   # drop them
```

Two identical calls make one request; a different filter is a different question and is
never served a stale answer.

### Anything not surfaced

```python
company.raw          # the listing row, exactly as the API sent it
employee.raw

api.transport.get_json("/api/countries")   # any endpoint, authenticated
```

## Errors

Every failure is a subclass of `NmbrsError`, and messages never contain tokens —
redaction happens when the exception is built, so they are safe to log and safe to paste
into an issue.

```python
from nmbrs_rest.errors import (
    InsufficientScopeError,
    NmbrsError,
    RateLimitError,
    ReauthorizationRequired,
    ResourceNotFoundError,
)

try:
    employee.salaries()
except InsufficientScopeError as exc:
    print("re-consent with:", exc.missing)
except ResourceNotFoundError:
    ...
except RateLimitError as exc:
    print("retry after", exc.retry_after)
except ReauthorizationRequired:
    ...   # refresh token dead — send the user through consent again
except NmbrsError as exc:
    ...   # everything else
```

**A 403 names the scope you are missing.** The spec declares required scopes per
operation, so the SDK can tell you which one to re-consent with instead of saying
"Forbidden":

```
InsufficientScopeError: [403/40303] GET /api/companies/ad3562fc/employees/salaries: no detail provided

  This operation accepts any of:  employee.employment, employee.employment.read
  Your token was granted:         company.info.read, employee.info.read

  Scope is fixed at consent time and cannot be widened for an existing
  token. Re-run the authorization flow including one of the scopes above.
```

Rate limits and transient 5xx are retried automatically with jittered backoff. Quota
exhaustion (`QuotaExceededError`) is not retried, because it would not help.

Every error code and what to do about it:
[docs/errors.md](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/docs/errors.md).

## Scopes

```python
from nmbrs_rest import ALL_READ_SCOPES, DEFAULT_SCOPES

api.login(redirect_uri, DEFAULT_SCOPES)              # small starter set
api.login(redirect_uri, sorted(ALL_READ_SCOPES))     # every read scope + offline_access
```

Ask for what you use. Requesting sixteen scopes, or a write scope you will never call,
looks bad on a customer's consent screen — and scope cannot be widened later without
re-consent.

Scope names do not reliably track resource names: `GET /api/debtors` requires
`company.info*`, not `debtor.info.read`. When you get it wrong, the 403 tells you
exactly which scope to add.

## What this hides

Nmbrs' REST API is company-scoped and inconsistent in ways that leak into every
integration written against it. The SDK absorbs that:

- **Responses are wrapped twice.** Everything arrives as `{"data": [...]}`, even a
  single record, and employee reads are wrapped again as
  `{"employeeId": ..., "contracts": [...]}` — with a payload key that differs per
  endpoint. You get the payload.
- **Three endpoints ignore `employeeId`.** `privateInfos`, `extraFields` and
  `useraccounts` return the whole company whatever you ask for. The SDK filters them
  client-side so `employee.private_info()` means what it says.
- **`/api/companies` refuses multi-debtor consent.** If your token spans several
  debtors that endpoint returns a 403; `api.companies()` catches it and walks debtors
  instead, transparently.
- **Paging is manual.** Every list read follows pages until they run out.
- **Dates need ISO-8601 strings.** Pass `date`/`datetime` objects instead.

## Example project

[`example/`](https://github.com/LarsKluijtmans/nmbrs_rest_api/tree/main/example) is a
small runnable project:

| File | What it shows |
| --- | --- |
| `main.py` | Consent in the browser, exchange the code, save the refresh token |
| `resume.py` | Running headless from the saved token — a cron job or backend service |
| `explore.py` | Filters, caching, errors worth catching, raw access |
| `callback.py` | A tiny HTTP server that catches the OAuth redirect |

```bash
cd example
pip install -r requirements.txt
cp .env.example .env      # then fill in your credentials
python main.py
```

## Features

- **Automatic pagination** — every list read follows pages until they run out.
- **Per-object caching** — keyed on the filter arguments, so the same question is asked
  once and a different question is not served a stale answer.
- **OAuth 2.0 handled end to end** — `login()`, `authenticate()`, refresh-on-401 with
  replay, and rotation persisted before use.
- **Meaningful errors** — a 403 tells you *which scope* is missing for *which
  operation*, not just "Forbidden".
- **Typed** — ships `py.typed`; read methods generated from the official OpenAPI spec,
  with CI failing if they drift from it.

## Reporting bugs

**Please open an issue.** This SDK is new and the API it wraps is unversioned and
occasionally surprising, so real-world reports are how the rough edges get found. Fixes
have already shipped because someone hit a 403 the SDK described badly.

### [→ Open an issue](https://github.com/LarsKluijtmans/nmbrs_rest_api/issues/new)

Useful to include:

- What you called, and what you expected to happen.
- The full exception. **Tokens are redacted before the message is built**, so exception
  text is safe to paste. Do not paste your `.env`, a raw token, or your subscription key.
- `nmbrs_rest.__version__` and your Python version.

Feature requests and questions are welcome in the same place. If you would rather fix it
yourself, see
[CONTRIBUTING.md](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/CONTRIBUTING.md).

## Documentation

- [Design](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/DESIGN.md) — architecture and the full API surface
- [Authentication](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/docs/authentication.md) — OAuth flow, and how to save and keep tokens
- [Errors](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/docs/errors.md) — every error code and what to do about it
- [Example project](https://github.com/LarsKluijtmans/nmbrs_rest_api/tree/main/example) — a runnable walkthrough
- [Releasing](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/docs/releasing.md) — publishing to TestPyPI and PyPI
- [Contributing](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/CONTRIBUTING.md)

Upstream API reference: [Nmbrs Public REST API](https://nmbrs.stoplight.io/docs/nmbrs-restapi).

## Scope of this release

Reads only. All 84 GET operations are implemented: 34 employee reads, 19 company reads,
7 debtor reads, plus the listings. The 39 write operations are planned for a later
release.

Nmbrs offers no sandbox. Development and testing need a Nmbrs demo environment, which
does not expire.

## Relationship to the SOAP SDK

Nmbrs has two APIs, and this project covers one of them:

| | Package | Import | Covers |
|---|---|---|---|
| SOAP | [`nmbrs`](https://pypi.org/project/nmbrs/) ([repo](https://github.com/LarsKluijtmans/nmbrs_api)) | `nmbrs` | The legacy SOAP API, retiring **2027-03-01** |
| REST | `nmbrs-rest-api` (this one) | `nmbrs_rest` | The current REST API |

Both are by the same author. The import names differ deliberately so the two can be
installed side by side while you migrate. The REST API does not yet cover everything
SOAP does, so a period of running both is expected.

## A note on upstream stability

The Nmbrs REST API is **unversioned**. Nmbrs ships additive changes without notice and
without a version bump. New fields simply appear — reads return dicts, so they arrive
without breaking anything. A field removed or retyped upstream is a real break, and
regenerating from the spec surfaces it as a failing check rather than a silent change.

## License

Apache-2.0. See [LICENSE](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/LICENSE).
