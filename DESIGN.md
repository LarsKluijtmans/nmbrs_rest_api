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
So a bare `api.employee(id)` cannot reach most of its own data without first
discovering which company owns it.

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

```python
from nmbrs_rest import Nmbrs

api = Nmbrs(
    subscription_key="30d05593229f49c18856be06ebc47b24",
    access_token="...",
    refresh_token="...",              # optional; enables auto-refresh
    client_id="...",                  # required to refresh
    client_secret="...",
    on_token_refresh=lambda tok: db.save(tok),   # rotating refresh tokens must be persisted
)
```

OAuth helpers live beside the client and require no `Nmbrs` instance:

```python
from nmbrs_rest.auth import OAuth

oauth = OAuth(client_id, client_secret, redirect_uri)
url   = oauth.authorization_url(scopes=[...], state=...)        # standard flow
url   = oauth.authorization_url(scopes=[...], state=..., par=True)  # PAR: POSTs /connect/par first
token = oauth.exchange_code(code)     # -> Token(access_token, refresh_token, expires_at, scopes)
token = oauth.refresh(refresh_token)
```

### 3.2 Entry points

```python
api.debtors()                  # -> Page[Debtor], auto-paginating iterator
api.debtor(debtor_id)          # -> Debtor  (no request yet)

api.companies()                # -> Page[Company]
api.company(company_id)        # -> Company (no request yet)

api.employee(employee_id)      # -> Employee (no request yet, company resolved on demand)

api.countries()                # static list
api.user_info()
api.subscription("hire")       # "hire" | "perform"
api.document(task_id)
api.salary_table(salary_table_id)
api.end_contract_reasons(year)
```

### 3.3 Debtor

```python
d = api.debtor(debtor_id)
d.info                    # GET /api/debtors/info, matched on this debtor
d.companies               # -> list[Company]
d.departments
d.functions
d.managers
d.manager_user_accounts
d.absence_case_managers
d.accountant_contact
d.tags
```

### 3.4 Company

```python
c = api.company(company_id)

c.employees()             # -> Page[Employee]   GET /api/companies/{id}/employees
c.employees(employee_type="payroll,formerPayroll", created_from=...)
c.employee(employee_id)   # -> Employee, company already known (no resolution needed)

c.name, c.number, c.debtor_id   # from the company list payload; lazy-fetched if unknown
c.period                        # GET /companies/{id}/period

c.addresses
c.bank_accounts
c.contact_persons
c.cost_centers
c.cost_units
c.hour_codes
c.leave_groups
c.schedules(year=..., period=...)
c.salary_tables
c.salary_table_content(version_id)
c.svw_settings(year=..., period=...)
c.wage_models(year=..., period=...)
c.fixed_wage_components(year=..., period=...)
c.variable_wage_components(year=...)
c.extra_field_settings
c.default_templates
c.wage_taxes
c.work_costs(year=...)
c.pension_export

c.runs(year=...)          # -> list[PayrollRun]
c.run(payroll_run_id, year=...)
```

**Bulk prefetch.** Because employee sub-resources live on company-wide endpoints, reading
one field across many employees one at a time is N requests against the *same* endpoint.
`prefetch` makes the single paginated pass and populates every employee's cache:

```python
c.prefetch("contracts", "salaries")   # one paginated pass each
for e in c.employees():
    e.contracts                       # cache hit, no request
```

This is the payoff of the lazy-object design rather than a workaround for it — the naive
loop stays correct, it is just slower.

### 3.5 PayrollRun

`year` is a **required** query param on the journal and SEPA endpoints, so it is
bound at construction and reused.

```python
r = c.run(run_id, year=2025)
r.employees
r.journals
r.journals_by_cost_center
r.journals_by_cost_center_unit
r.journals_by_department
r.journals_by_employee
r.sepa(payment_date=None)
r.wage_codes_xml(wage_codes=[100, 101])
```

### 3.6 Employee

```python
e = api.employee(employee_id)          # or api.company(cid).employee(eid)

# --- from GET /api/employees/{id}, one request fills all five ---
e.personal_info
e.address
e.department
e.function
e.manager

# --- company-scoped, filtered by employeeId ---
e.contracts
e.employments
e.salaries
e.schedules
e.bank_accounts
e.cost_centers
e.cost_per_hour(year=..., period=...)
e.absences
e.leave_requests(year=..., status=..., type=..., leave_group_id=...)
e.leave_balances(leave_group_id=...)
e.parental_leave(year=...)
e.fixed_wage_components(year=..., period=...)
e.variable_wage_components(year=..., period=...)
e.svw_settings
e.wage_tax_settings
e.labour_agreement_settings
e.lease_car
e.children

# --- company-scoped, no employeeId filter: fetched whole, filtered locally ---
e.extra_fields
e.private_info
e.user_account

# --- employee-scoped ---
e.fixed_hours(year=..., period=...)
e.variable_hours(year=..., period=...)
e.fixed_days(year=..., period=...)
e.variable_days(year=..., period=...)
e.document_folders
e.document_types
e.payslip(year=..., period=...)
e.annual_statement(year=...)

# --- housekeeping ---
e.company                 # -> Company (triggers resolution if unknown)
e.refresh()               # drop this object's cache
e.loaded                  # {"personal_info", "contracts"} — what's actually been fetched
e.to_dict()               # dump only what's loaded; does not trigger requests
```

Parameterised fields (`year`, `period`, …) are **methods**, not properties.
Unparameterised fields are properties. This keeps `e.contracts` clean while making
it obvious that `e.leave_requests(year=2025)` varies by argument. Each distinct
argument set gets its own cache entry.

---

## 4. Company resolution (the `api.employee(id)` path)

`Nmbrs` holds an **in-memory** index — it lives and dies with the client instance,
nothing is written to disk:

```python
self._employee_company: dict[EmployeeId, CompanyId] = {}
self._companies: list[Company] | None = None
```

**Population — free path.** Every time the SDK sees an employee inside a company
context, it records the mapping. So `api.company(cid).employees()` indexes the whole
company for free, and `api.company(cid).employee(eid)` never needs resolution.

**Population — resolution path.** When a company-scoped field is accessed on an
employee whose company is unknown:

1. `GET /api/companies` (paginated, cached on the client) — all companies the token can see.
2. For each company: `GET /api/companies/{cid}/employees?employeeId={eid}&pageSize=1`
3. First non-empty `data` wins → cached in `_employee_company`.
4. Nothing found → `EmployeeNotFoundError`.

Worst case is `1 + N` requests for `N` visible companies, paid **once per client
instance**. `e.personal_info` and the other employee-scoped fields never trigger it.

Escape hatches, no resolution performed:

```python
api.employee(eid, company_id=cid)
api.company(cid).employee(eid)
api.prime(company_id)      # index one company's employees up front
```

---

## 5. Internals

```
src/nmbrs_rest/
  __init__.py            Nmbrs, exceptions, Token
  client.py              Nmbrs facade + in-memory company index
  auth.py                OAuth (authorize / PAR / exchange / refresh), Token, auto-refresh
  transport.py           httpx wrapper: headers, retry/backoff, error mapping
  pagination.py          Page — lazy auto-paginating iterator
  errors.py              RFC 7807 -> exception hierarchy
  lazy.py                lazy_field / lazy_method descriptors + per-object cache
  resources/
    base.py              Resource: identity, cache, refresh(), loaded, to_dict()
    debtor.py
    company.py
    employee.py
    payroll_run.py
    static.py
  models/
    __init__.py          curated re-exports with stable names
    _generated.py        pydantic v2, generated — do not edit
  _spec/
    nmbrs-openapi.yaml   vendored spec, provenance recorded
tools/
  fetch_spec.py          pull the spec from Stoplight
  generate_models.py     spec -> models/_generated.py
tests/
```

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

Generated with `datamodel-code-generator` from the vendored spec into
`models/_generated.py`; `models/__init__.py` re-exports a curated set under stable
names so a spec rename doesn't break user imports.

- pydantic v2, `model_config = ConfigDict(extra="allow")` — the API is additive-only
  and unversioned, so unknown fields must survive rather than blow up.
- Field aliases map the API's `camelCase` to Python `snake_case`.
- `format: uuid` → `UUID`, `format: date-time` → `datetime`, `format: date` → `date`.
- `tools/generate_models.py` is checked in; regenerating is a reviewable diff.

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

## 9. Open points for review

1. **Resolution cost.** For a token that can see many companies, a cold
   `api.employee(id).contracts` costs `1 + N` requests. Acceptable, or should
   `api.employee()` warn/require opt-in above some company count?
2. **`e.address` vs `e.addresses`.** `GET /api/employees/{id}` returns one address,
   but `/companies/{cid}/employees/addresses` returns a list per employee.
   Proposal: `e.address` = the default from the cheap call, `e.addresses` = the full list.
3. **`year`/`period` defaults.** Several endpoints return the current period when
   `year`/`period` are omitted. Proposal: pass through unset rather than defaulting
   to `company.period`, so behaviour matches the API exactly.
4. **Country variants.** The spec is titled `version: Global`. If NL/SE-specific
   fields exist behind the same paths, `extra="allow"` covers reading them, but
   typed access would need per-country model overlays. Deferred until we see one.
