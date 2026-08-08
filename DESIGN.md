# nmbrs_rest_api — SDK Design

Python SDK for the [Nmbrs Public REST API](https://nmbrs.stoplight.io/docs/nmbrs-restapi).

Status: **design draft, for review. No code written yet.**

---

## 1. Context

We want an object-oriented, lazy-loading client:

```python
api = Nmbrs(...)
emp = api.employee(employee_id)
emp.personal_info      # fetched on first access
emp.contracts          # fetched on first access, cached
```

The same shape for `Company`, `Debtor`, and `PayrollRun`.

This design is derived from the actual OpenAPI 3.0.1 spec, not the rendered docs.
The spec is retrievable (unauthenticated) at:

```
https://nmbrs.stoplight.io/api/v1/projects/nmbrs/nmbrs-restapi/nodes/api-design%2Fnmbrs-api-Global.v1.yaml
```

**125 operations** (85 GET, 40 write), **~230 schemas**, 26 tags.

---

## 2. What the API actually looks like

| | |
|---|---|
| Base URL | `https://api.nmbrsapp.com` |
| Auth | OAuth 2.0 **authorization code only** (no client_credentials), optional PAR variant |
| Identity server | `https://identityservice.nmbrs.com` |
| Required headers | `Authorization: Bearer <token>` **and** `X-Subscription-Key: <key>` |
| Token lifetimes | access token 1 h; refresh token 30 d, **single-use / rotating** |
| Versioning | none — no URL/header/query version. Additive changes only |
| Pagination | `pageNumber` (from 1), `pageSize` (default 20, **max 100**) |
| Response envelope | `{ "data": [...], "pagination": {...} }` — **always a list**, even for single-item reads |
| Errors | RFC 7807: `type`, `httpStatus`, `code`, `title`, `detail`, `invalid-params[]`, `docUrl` |
| Sandbox | none — testing needs a non-expiring Nmbrs demo environment |
| IDs | UUIDs everywhere |

### 2.1 The constraint that drives the whole design

The API is **company-scoped, not employee-scoped**.

Only these reads are keyed by employee id alone:

```
GET /api/employees/{employeeId}                  -> personalInfo, manager, department, function, address
GET /api/employees/{employeeId}/fixedhours       ?year&period
GET /api/employees/{employeeId}/variablehours    ?year&period
GET /api/employees/{employeeId}/fixeddays        ?year&period
GET /api/employees/{employeeId}/variabledays     ?year&period
GET /api/employees/{employeeId}/documents/folders
GET /api/employees/{employeeId}/documents/types
GET /api/employees/{employeeId}/annualstatement  ?year
GET /api/employees/{employeeId}/payslipperperiod ?year&period
```

**Everything else** about an employee — contracts, salaries, employments, schedules,
absences, leave, wage components, bank accounts, SVW/wage-tax settings, lease cars,
children, cost centers, … — is only readable through a **company-wide** endpoint:

```
GET /api/companies/{companyId}/employees/{resource}?employeeId={employeeId}
```

And critically: **`GET /api/employees/{employeeId}` does not return the `companyId`.**
There is no employee-to-company lookup anywhere in the API, which is why
`api.employee()` takes both ids rather than resolving one from the other (§4).

Three of those company-wide endpoints don't even accept an `employeeId` filter and
must be fetched whole and filtered client-side:

| Endpoint | Available filters |
|---|---|
| `/employees/extraFields` | `extraFieldType` only |
| `/employees/privateInfos` | `createdFrom` only |
| `/employees/useraccounts` | none |

---

## 3. Public API surface

### 3.1 Construction

`Nmbrs` owns the whole lifecycle: credentials, consent, tokens, and the reads they
unlock. The three credentials that are always needed are positional.

```python
from nmbrs_rest import Nmbrs

api = Nmbrs(client_id, client_secret, subscription_key)
```

Optional keyword arguments cover resuming and persistence:

```python
api = Nmbrs(
    client_id, client_secret, subscription_key,
    refresh_token=saved,                     # skip the browser entirely
    on_token_refresh=lambda tok: db.save(tok),   # told on every rotation
    redirect_uri="https://app.example/callback",
)
```

`OAuth`, `Transport`, `Page` and the token stores remain importable for anyone who
wants to assemble their own stack; `Nmbrs` is a facade over them, not a replacement.

### 3.2 The authorization flow

Nmbrs supports the authorization code flow only, so the first token always needs a
human. Two calls:

```python
url = api.login(redirect_uri, scopes)   # -> str, send the user here
api.authenticate(code)                  # code from the redirect

api.access_token       # live properties, not snapshots
api.refresh_token
api.scopes             # what was actually granted
api.expires_at
```

`login()` remembers the CSRF `state`, the PKCE verifier and the redirect URI on the
instance, which is all a script needs. RFC 6749 §4.1.3 requires the token exchange to
present the *same* redirect URI as the authorization request, so carrying it is not
optional. A web app handles the redirect in a different request, so both can be passed
back explicitly:

```python
url = api.login(redirect_uri, scopes, pkce=True)
state, verifier = api.pending_login.state, api.pending_login.code_verifier
# ... later ...
api.authenticate(code, state=state, code_verifier=verifier)
```

`api.refresh()` forces a refresh; `api.logout()` revokes upstream and clears local state.

**Rotation.** Nmbrs kills the old refresh token whenever it issues a new one. The token
properties are live so they never go stale in place, but an application that *persists*
them needs `on_token_refresh` — otherwise it stores a value that is dead by the time the
process restarts. The callback fires after the in-memory copy is updated, so a failure
is loud without leaving the client unusable.

### 3.3 Entry points

```python
api.debtors()                          # -> list[Debtor]
api.debtor(debtor_id)                  # -> Debtor  (no request)

api.companies()                        # -> list[Company]
api.company(company_id)                # -> Company (no request)

api.employees(company_id)              # -> list[Employee]
api.employee(company_id, employee_id)  # -> Employee, one request
```

Collections are eager: every page is fetched before the list is returned. `Page` remains
available for streaming a large company without holding it in memory.

`api.company(id)` returns the *same* object for the same id within a session. Caching
lives on the resource, so handing back a fresh object each time would silently discard it.

### 3.4 Reads are methods

Attributes cannot express a filter, and 33 of the 38 employee endpoints take at least
one — `year`, `period`, `created_from`, `changed_from`. So every read is a method, and
the parentheses also mark where I/O happens:

```python
employee.contracts()
employee.salaries(created_from=date(2026, 1, 1))
employee.fixed_hours(year=2026, period=3)
employee.leave_requests(year=2026, status="Approved", request_type="Holiday")
```

Cheap identity fields come free with the company listing and are plain attributes:

```python
employee.id, employee.company_id
employee.first_name, employee.last_name, employee.prefix, employee.initials
employee.employee_number, employee.employee_type, employee.full_name
```

`employee.details()` fetches the composite record from `GET /api/employees/{id}`
(`personalInfo`, `manager`, `department`, `function`, `address`) in one request.

Company and debtor reads work the same way — `company.period()`,
`company.wage_taxes(year=2026)`, `debtor.tags()` — and `debtor.companies()` returns
`Company` objects rather than dicts.

### 3.5 Caching

Per object, keyed on the *normalised filter arguments*, not just the endpoint. Two
identical calls are one request; a different filter is a different question and must not
be served a stale answer:

```python
employee.contracts()                              # request
employee.contracts()                              # cached
employee.contracts(created_from=date(2026, 1, 1)) # request
employee.cached                                   # 2 entries
employee.refresh()                                # drop them
```

Caching is deliberately per object rather than global: a shared cache would need
invalidation rules the API gives us no way to write.

### 3.6 What the SDK normalises

| Upstream behaviour | What the caller sees |
|---|---|
| Everything wrapped in `{"data": [...]}`, even single records | the record, or the list |
| Employee reads wrapped again as `{"employeeId": ..., "<payloadKey>": ...}`, key differing per endpoint | the payload |
| `privateInfos`, `extraFields`, `useraccounts` ignore `employeeId` | filtered client-side, so the method means what it says |
| Manual `pageNumber`/`pageSize` paging | pages followed automatically |
| `date`/`datetime` filters needing ISO-8601 strings | pass Python objects |
| `type` as a query parameter name | `request_type`, since `type` shadows a builtin |
| Path segments like `costperhour`, `fixedWageComponents`, `privateInfos` | `cost_per_hour`, `fixed_wage_components`, `private_info` |

### 3.7 Generation

The read surface is generated from the vendored spec by `tools/generate_resources.py`
into `resources/_generated.py`: 34 employee reads, 19 company reads, 7 debtor reads.

Endpoint paths, filter names and the per-endpoint payload key come from the spec. Method
*names* come from curated maps in the generator, because the spec's own segments are
inconsistent and mechanical snake_casing produces a surface nobody would design on
purpose. Those maps are asserted exhaustive against the spec, so an endpoint that appears
or disappears upstream fails generation rather than silently vanishing from the SDK. CI
runs `--check`.

---

## 4. Why `api.employee()` takes both ids

Nmbrs exposes no employee-to-company lookup. `GET /api/employees/{employeeId}` returns
the employee's own record but not its `companyId`, and every other employee read lives
under `/api/companies/{companyId}/employees/...`.

An earlier draft resolved the company by scanning every visible company until the
employee turned up, caching the mapping in memory. That was dropped. It made a single
innocuous-looking call cost up to one request per company, with a cost that depended on
consent breadth and on which company happened to be listed first — unpredictable in
exactly the way an SDK should not be.

So both ids are required:

```python
employee = api.employee(company_id, employee_id)
```

This costs exactly one request. The listing endpoint accepts `?employeeId=`, so it does
not page through the company. An id that belongs elsewhere raises `ResourceNotFoundError`
naming both ids, which is also how you discover an employee moved.

Most flows have the company id already, because they arrived through
`api.companies()` or `api.employees(company_id)`.
## 5. Internals

```
src/nmbrs_rest/
  __init__.py            Nmbrs, resources, exceptions, Token
  client.py              Nmbrs facade: credentials, consent, tokens, entry points
  auth.py                OAuth (authorize / PAR / PKCE / exchange / refresh / revoke)
  tokens.py              Token + TokenStore: memory, file, keyring, callback
  transport.py           httpx wrapper: headers, refresh-on-401, retry/backoff
  pagination.py          Page — lazy auto-paginating iterator, unwrap_one
  errors.py              RFC 7807 -> exception hierarchy, scope-aware 403
  _scopes.py             generated: 123 operations -> required scopes
  resources/
    base.py              Resource: path building, paging, per-argument cache
    _generated.py        generated: 60 typed read methods + the payload-key table
    debtor.py
    company.py
    employee.py
  _spec/
    nmbrs-openapi.yaml   vendored spec, provenance recorded
tools/
  fetch_spec.py          pull the spec from Stoplight
  generate_scopes.py     spec -> _scopes.py            (--check in CI)
  generate_resources.py  spec -> resources/_generated.py  (--check in CI)
scripts/
  login.py               run the authorization flow, save tokens
  try_testpypi.py        install the staged package and verify it
  verify_install.py      checks that run against an installed artifact
tests/
```

`PayrollRun` and the static reads (`countries`, `user_info`, `subscription`,
`document`, `salary_table`, `end_contract_reasons`) are not implemented yet; the 7 run
endpoints and 5 standalone ones are excluded from generation for now.

### 5.1 Transport

- `httpx.Client`, connection pooling, configurable timeout.
- Injects `Authorization` and `X-Subscription-Key` on every request.
- **401** → refresh the token once, replay the request, fire `on_token_refresh`.
  A rotating refresh token means the callback *must* fire or the caller is locked out.
- **429** → `Too_Many_Calls` (42908): exponential backoff with jitter, bounded retries.
  `Quota_Exceeded` (42909): raise immediately, retrying won't help.
- **502/503** → bounded retry with backoff. **500** → raise.
- Refresh is guarded by a lock so concurrent callers don't burn the single-use token twice.

### 5.2 Pagination

`Page` is a lazy iterator, not a materialised list:

```python
for emp in company.employees():        # fetches page 1, then 2, … on demand
    ...

page = company.employees()
page.total_records                     # from the pagination envelope
list(page)                             # materialise if you want
page.first()                           # stop after one record
```

Default `pageSize=100` (the maximum) to minimise round trips; overridable.

Because the envelope always wraps a list, single-item reads such as
`GET /api/employees/{id}` unwrap `data[0]` and raise `NotFoundError` on an empty list.

### 5.3 Models

**Not implemented yet.** Reads currently return `dict[str, Any]` exactly as the API
sent them, minus the envelope and the per-employee wrapper. `Token` is the only
pydantic model in the package today.

The intended shape, once built:

- Generated from the vendored spec into `models/_generated.py`, with
  `models/__init__.py` re-exporting a curated set under stable names so a spec rename
  does not break user imports.
- pydantic v2, `model_config = ConfigDict(extra="allow")` — the API is additive-only
  and unversioned, so unknown fields must survive rather than blow up.
- Field aliases map the API's `camelCase` to Python `snake_case`.
- `format: uuid` → `UUID`, `format: date-time` → `datetime`, `format: date` → `date`.

`tools/generate_resources.py` already derives the payload key and JSON type per
endpoint, so the wiring point for models is known.

### 5.4 Errors

```
NmbrsError
├── AuthenticationError        401 / type=authenticationError
│   └── TokenExpiredError      40102 (auto-refresh handles this; raised only if refresh fails)
├── PermissionError            403 — incl. 40305 "no access to this company/debtor"
├── NotFoundError              404
├── ValidationError            400 type=validationError    -> .invalid_params
├── InvalidRequestError        400 type=invalidRequestError
├── RateLimitError             429 type=throttlingError
│   └── QuotaExceededError     42909
├── ServerError                500 / 502 / 503
└── EmployeeNotFoundError      SDK-level: company resolution exhausted
```

Every exception exposes `code`, `title`, `detail`, `doc_url`, `invalid_params`,
`http_status`, plus the originating `request` for debugging.

---

## 6. Scope

**v1 — reads (85 GET operations).** Everything in §3. Lazy loading, pagination,
auth + refresh, error mapping, generated models.

**v2 — writes (40 operations).** Explicit methods, never attribute assignment:

```python
e.update_personal_info(...)      e.create_contract(...)       e.delete_contract(id)
e.create_employment(...)         e.create_salary(...)         e.create_schedule(...)
e.create_address(...)            e.create_bank_account(...)   e.update_bank_account(...)
e.create_absence(...)            e.create_leave_request(...)  e.upload_document(...)
company.create_employee(...)     ...
```

Mutations invalidate the relevant cache entry on the affected object.

**Out of scope for now:** async client (transport is abstracted so `AsyncNmbrs` can be
added without redesign), webhooks (none in the spec), the legacy SOAP API
(Nmbrs retires it 2027-03-01).

---

## 7. Testing

No sandbox exists. Three layers:

1. **Unit** — `respx` mocks over httpx. Covers pagination, 401-refresh-replay,
   429 backoff, error mapping, lazy-cache behaviour, company resolution.
2. **Contract** — responses validated against the vendored spec, so a spec update
   that breaks our assumptions fails CI.
3. **Live smoke** — opt-in via env vars against a Nmbrs demo environment, read-only,
   skipped by default.

Tooling: `pytest`, `ruff`, `mypy --strict`, `uv`. Python 3.10+.

---

## 8. Distribution

This is a public, open-source SDK.

| | |
|---|---|
| PyPI | `nmbrs-rest-api` |
| Import | `nmbrs_rest` |
| License | Apache-2.0 |
| Source | https://github.com/LarsKluijtmans/nmbrs_rest_api |

The import name is not `nmbrs` because that name belongs to the separate Nmbrs **SOAP**
SDK by the same author. SOAP is supported until 2027-03-01, so users migrating will have
both installed at once and the two must coexist.

Version is derived from git tags; `pyproject.toml` carries no version field. Staging
publishes to TestPyPI on demand, live publishes to PyPI on a `v*` tag behind a manual
approval gate. See [docs/releasing.md](docs/releasing.md).

## 9. Decisions taken, and what is still open

Resolved since the first review:

| Question | Decision |
|---|---|
| Reads as attributes or methods? | **Methods.** 33 of 38 employee endpoints take a filter; an attribute cannot express `year`/`period`/`created_from`. |
| Collections eager or lazy? | **Eager lists.** `Page` stays available for streaming. |
| `api.employee(id)` without a company? | **Dropped.** Both ids required — see §4. |
| Where does auth live? | **On `Nmbrs`.** `login()` / `authenticate()` / live token properties. |

Still open:

1. **Typed models.** Reads currently return `dict[str, Any]`. Generating pydantic models
   from the spec's response schemas is the next step; the generator already extracts the
   payload key and type per endpoint, so the shape information is in hand.
2. **Bulk prefetch.** Omitting `employeeId` returns every employee's rows in one
   paginated pass, turning N requests into one. A supported `Company.prefetch(...)` that
   populates each employee's cache is worth having — see `docs/errors.md`, *Reducing
   request volume*, for the manual version.
3. **`address` vs `addresses`.** `GET /api/employees/{id}` returns one address inside
   `details()`, while `/companies/{cid}/employees/addresses` returns a list per employee
   via `employee.addresses()`. Both are reachable; whether they should be reconciled is
   open.
4. **Writes.** 39 POST/PUT/DELETE operations are unimplemented. They need a different
   safety story than reads: no automatic retry on timeout, and idempotency is not offered
   by the API.
5. **Country variants.** The spec is titled `version: Global`. If NL/SE-specific fields
   exist behind the same paths, dict returns already carry them; typed access would need
   per-country overlays. Deferred until one is seen.
