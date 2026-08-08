# Errors

Every documented Nmbrs error code, every SDK exception, and what to actually do about each.

> **Design stage.** This document specifies the error contract the implementation must
> meet. The code below is the intended API, not shipped behaviour.
> See [authentication.md](./authentication.md) for token and identity-server errors, and
> [../DESIGN.md](../DESIGN.md) for the overall design.

## How Nmbrs reports errors

[RFC 7807](https://datatracker.ietf.org/doc/html/rfc7807) problem details:

```json
{
  "type": "validationError",
  "httpStatus": 400,
  "code": 40033,
  "title": "Parameter_Invalid",
  "detail": "Invalid parameter.",
  "invalid-params": [
    { "name": "year", "reason": "The parameter is invalid. It needs to be a valid year." }
  ],
  "docUrl": "https://developer.nmbrs.com/docs/errors"
}
```

The key is `invalid-params` — **hyphenated**, not `invalid_params`. The SDK exposes it as
`.invalid_params`.

### Error types

| `type` | Meaning |
|---|---|
| `authenticationError` | Failed to authenticate. Used for **both** 401 and 403 |
| `invalidRequestError` | Invalid parameters per business rules (bad leave type, unknown labour agreement) |
| `validationError` | Field-level validation failure (wrong format, missing required parameter, wrong type) |
| `throttlingError` | Too many requests |
| `apiError` | Anything else, typically a Nmbrs-side problem |

> Nmbrs' own documentation names the rate-limit type `rateLimitError`, but every example in
> the OpenAPI spec uses `throttlingError`. The SDK matches on either.

### The code list is not exhaustive

Thirteen numeric codes are documented. Nmbrs' public error page documents only *types* and
HTTP statuses — no numeric codes at all — so undocumented codes exist in the wild. The
mapper degrades to a sensible class rather than failing on an unknown code, and preserves
the raw payload so you can see what actually arrived.

## Exception hierarchy

```
NmbrsError
├── NmbrsConfigError                 bad SDK setup, raised before any request
├── TransportError                   no usable HTTP response
│   ├── NmbrsTimeoutError
│   └── NmbrsConnectionError
├── IdentityServerError              from identityservice.nmbrs.com (RFC 6749)
│   ├── InvalidGrantError
│   ├── InvalidClientError
│   └── ReauthorizationRequired      terminal: the user must consent again
├── TokenStoreError                  load/save/delete failed
├── APIError                         any RFC 7807 response from api.nmbrsapp.com
│   ├── AuthenticationError          401
│   │   ├── MissingTokenError            40101
│   │   └── InvalidTokenError            40102
│   ├── PermissionError              403
│   │   ├── InsufficientScopeError       403 where a required scope was not granted
│   │   ├── DataAccessError              40303, 40305
│   │   └── SubscriptionError            40304
│   ├── NotFoundError                404
│   │   ├── ResourceNotFoundError        40401
│   │   └── CompanyNotFoundError         40404
│   ├── ValidationError              400 validationError, incl. 40033
│   ├── InvalidRequestError          400 invalidRequestError
│   ├── RateLimitError               429
│   │   └── QuotaExceededError           42909, not retryable
│   └── ServerError                  500, 502, 503
└── EmployeeResolutionError          SDK-level: owning company could not be determined
```

```python
class NmbrsError(Exception):
    """Base for everything this SDK raises."""


class APIError(NmbrsError):
    """An RFC 7807 error response from the Nmbrs REST API."""

    def __init__(
        self,
        *,
        http_status: int,
        code: int | None,
        title: str | None,
        detail: str | None,
        type_: str | None,
        invalid_params: tuple[InvalidParam, ...] = (),
        doc_url: str | None = None,
        method: str | None = None,
        path: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.http_status = http_status
        self.code = code
        self.title = title
        self.detail = detail
        self.type = type_
        self.invalid_params = invalid_params
        self.doc_url = doc_url
        self.method = method
        self.path = path
        self.request_id = request_id
        super().__init__(self._render())

    def _render(self) -> str:
        where = f"{self.method} {self.path}" if self.path else "request"
        head = f"[{self.http_status}"
        head += f"/{self.code}" if self.code is not None else ""
        head += f"] {where}: {self.detail or self.title or 'no detail provided'}"
        for p in self.invalid_params:
            head += f"\n  - {p.name}: {p.reason}"
        return head
```

Exception messages and `repr()` never contain a bearer token, refresh token, client secret
or subscription key. Redaction happens at construction, not at print time.

## Response to exception

Precedence is **numeric code → `type` → HTTP status**. Most specific wins; the status is
the last resort so an unrecognised code still lands somewhere useful.

```python
_BY_CODE: dict[int, type[APIError]] = {
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

_BY_TYPE: dict[str, type[APIError]] = {
    "authenticationError": AuthenticationError,   # refined by status below
    "invalidRequestError": InvalidRequestError,
    "validationError": ValidationError,
    "throttlingError": RateLimitError,
    "rateLimitError": RateLimitError,             # docs name; spec uses throttlingError
    "apiError": ServerError,
}

_BY_STATUS: dict[int, type[APIError]] = {
    400: ValidationError,
    401: AuthenticationError,
    403: PermissionError,
    404: NotFoundError,
    429: RateLimitError,
    500: ServerError,
    502: ServerError,
    503: ServerError,
}


def exception_for(response: httpx.Response, operation: Operation) -> APIError:
    payload = _safe_problem_json(response)      # tolerates HTML and empty bodies
    code = payload.get("code")
    type_ = payload.get("type")

    cls = _BY_CODE.get(code) if isinstance(code, int) else None

    # authenticationError spans 401 and 403; disambiguate on status.
    if cls is None and type_ == "authenticationError":
        cls = AuthenticationError if response.status_code == 401 else PermissionError
    if cls is None and isinstance(type_, str):
        cls = _BY_TYPE.get(type_)
    if cls is None:
        cls = _BY_STATUS.get(response.status_code, APIError)

    # A 403 the token could never have satisfied is a scope problem, not a data problem.
    if cls is PermissionError and (missing := _missing_scopes(operation)):
        return InsufficientScopeError(missing=missing, operation=operation, **_fields(payload))

    return cls(**_fields(payload), method=operation.method, path=operation.path)
```

`_safe_problem_json` is load-bearing: gateways return HTML on 502/503 and bodies are
sometimes empty. It must never raise while constructing an error, or the real failure gets
masked by a `JSONDecodeError`.

## Error reference

### 400 — Bad request

#### 40033 `Parameter_Invalid` · `validationError`

Nmbrs says: *Invalid parameter.*

A parameter failed validation. The terse `detail` is useless on its own — the actual
information is in `invalid-params`, which the SDK always surfaces.

→ `ValidationError`

```
[400/40033] GET /api/companies/{companyId}/runs: Invalid parameter.
  - year: The parameter is invalid. It needs to be a valid year.
```

**Fix:** correct the named parameter. Common causes: `pageSize` above 100, a malformed
date, a non-UUID where a UUID is required, a `year` outside the supported range.

### 401 — Unauthorized

#### 40101 `Missing_Token` · `authenticationError`

Nmbrs says: *Token is missing on the authentication*

No `Authorization` header arrived. Usually a construction bug, not an expiry.

→ `MissingTokenError`

```
[401/40101] GET /api/companies: Token is missing on the authentication
```

**Fix:** check the client was given a token at all. The SDK raises `NmbrsConfigError`
before sending if it can tell locally.

#### 40102 `Invalid_Token` · `authenticationError`

Nmbrs says: *Token is invalid.*

Expired, malformed, or revoked access token.

→ `InvalidTokenError`

**Fix:** normally none — the SDK refreshes once and replays the request. If it recurs after
a successful refresh, the grant is dead: see
[recovery](./authentication.md#recovery).

### 403 — Forbidden

Three distinct causes, three different fixes. See [the three 403s](#the-three-403s).

#### 40303 `Unauthorized_AccessData` · `authenticationError`

Nmbrs says: *You do not have access for the debtor or company you are trying to reach.
Contact the administrator of the environment and review access rights by tags/filters for
your login on Template User.*

The token is valid and the scope is right, but the **consenting login** cannot see this
debtor or company.

→ `DataAccessError`

```
[403/40303] GET /api/companies/ad3562fc-.../employees: You do not have access for the
debtor or company you are trying to reach. The token has the required scope
(company.info.read), so this is a data-access restriction in Nmbrs, not a scope problem.
Ask the environment administrator to review access rights by tags/filters for this login.
```

**Fix:** the customer's Nmbrs administrator must grant the login access. Nothing you can
change in code. In a multi-tenant app this very often means you used tenant A's token
against tenant B's company.

#### 40304 `Invalid_Subscription` · `authenticationError`

Nmbrs says: *This environment is disabled, there is no valid subscription.*

The customer's Nmbrs environment is disabled — billing or contract, not permissions.

→ `SubscriptionError`

**Fix:** the customer must sort it out with Nmbrs. Retrying never helps. Surface it as
"your Nmbrs environment is inactive", not as an integration error.

#### 40305 — data access to the specific company or debtor

Documented only in prose, with no title or type given:

> *Means the user's OAuth token and permissions are fine, but they don't have access to the
> specific company or debtor requested. The authenticated user needs to check their data
> access configuration in Nmbrs.*

→ `DataAccessError`

**Fix:** as 40303. Treat them as the same remedy; the distinction is Nmbrs-internal.

#### Insufficient scope

Not a distinct Nmbrs code — the SDK detects it. When the operation requires a scope the
token was never granted, you get `InsufficientScopeError` instead of a bare
`PermissionError`. See below.

### 404 — Not found

#### 40401 `Not_Found` · `invalidRequestError`

Nmbrs says: *The requested resource could not be found.*

→ `ResourceNotFoundError`

**Fix:** check the id. Note a **single-item read returns an empty `data` array**, not a
404 — the SDK converts that to `ResourceNotFoundError` for you.

#### 40404 `Invalid_Company` · `invalidRequestError`

Nmbrs says: *Company not found. Check if the company Id is correct.*

→ `CompanyNotFoundError`

**Fix:** verify the company id. Distinct from 40401 because it is specifically the company
path parameter, which matters given how many endpoints are company-scoped. Note that a
company you *cannot see* returns 403, not 404.

### 429 — Too many requests

#### 42908 `Too_Many_Calls` · `throttlingError`

Nmbrs says: *The amount of calls is above the threshold for your subscription plan.*

Short-term throttle. **Retryable.**

→ `RateLimitError`

```
[429/42908] GET /api/companies/.../employees/contracts: The amount of calls is above the
threshold for your subscription plan. Retrying with backoff (attempt 2 of 5).
```

**Fix:** the SDK retries with exponential backoff and jitter. Persistent throttling means
you should raise `pageSize` to 100 and cut request count — see
[reducing request volume](#reducing-request-volume).

#### 42909 `Quota_Exceeded` · `throttlingError`

Nmbrs says: *Out of call volume quota.*

Your plan's call volume is exhausted. **Not retryable** — waiting inside the process will
not help, since the quota resets on a billing cycle, not in seconds.

→ `QuotaExceededError`

**Fix:** raise the plan, or reduce volume. The SDK raises immediately rather than burning
time on backoff.

### 500 / 502 / 503 — Server errors

| Code | Title | Nmbrs says | Retryable |
|---|---|---|---|
| 50001 | `Unkown` *(their spelling)* | An unexpected error has occurred. | No |
| 50201 | `Bad_Gateway` | A gateway error has ocurred. *(their spelling)* | Yes |
| 50301 | `Service_Unavailable` | The API is not available, it can be because of an update or an unexpected error. | Yes |

→ `ServerError`

502 and 503 are usually transient (deploys, gateway blips) and worth retrying. A 500 is a
genuine bug on Nmbrs' side; retrying rarely helps and it is worth reporting with the
request details.

These often arrive as **HTML, not JSON**, from an intervening gateway. The SDK still
produces a `ServerError` rather than a parse failure.

## Scope-aware 403 diagnosis

A bare "403 Forbidden" tells you nothing. Since all 123 operations declare their required
scopes in the OpenAPI spec, and the token response tells us what was actually granted, the
SDK can name the exact problem.

A scope table is generated from the vendored spec at build time:

```python
# nmbrs_rest/_scopes.py - GENERATED, do not edit
REQUIRED_SCOPES: dict[tuple[str, str], frozenset[str]] = {
    ("GET", "/api/companies/{companyId}/employees/salaries"):
        frozenset({"employee.employment", "employee.employment.read"}),
    ...
}
```

Granted scopes come from the token, so this is a local check needing no extra request:

```python
def _missing_scopes(operation: Operation) -> frozenset[str]:
    """Scopes that would satisfy this operation, none of which the token holds."""
    required = REQUIRED_SCOPES.get((operation.method, operation.template), frozenset())
    if not required or required & operation.granted_scopes:
        return frozenset()      # satisfied, so a 403 here means data access
    return required
```

Any one of the listed scopes satisfies the operation — the write scope always implies its
`.read` counterpart.

**Worked example.** You consented to `company.info.read` and `employee.info.read`, then
read salaries:

```python
company.employee(employee_id).salaries
```

```
nmbrs_rest.errors.InsufficientScopeError:
[403] GET /api/companies/{companyId}/employees/salaries: missing required scope.

  This operation accepts any of:  employee.employment, employee.employment.read
  Your token was granted:         company.info.read, employee.info.read, offline_access

  Scope is fixed at consent time and cannot be widened for an existing token.
  Re-run the authorization flow including 'employee.employment.read'.
```

Contrast with the same status where the scope *is* present — a completely different fix:

```
nmbrs_rest.errors.DataAccessError:
[403/40303] GET /api/companies/ad3562fc-.../employees/salaries: You do not have access for
the debtor or company you are trying to reach.

  Required scope employee.employment.read IS granted, so this is not a scope problem.
  The consenting Nmbrs login cannot see this company. Either the company belongs to a
  different debtor than the one this token was consented for, or the login needs its
  access rights (tags/filters) reviewed by the environment administrator.
```

That distinction — *scope missing* versus *scope fine, data invisible* — is the single most
useful thing this SDK does with errors, because the remedies have nothing in common: one is
a code change, the other is a customer configuration change.

### A gotcha worth knowing

Scope names do not always match the resource. `GET /api/debtors` requires
`company.info`/`company.info.read`, **not** `debtor.info.read`. Trust the generated table,
not intuition. The full mapping is in [authentication.md](./authentication.md#scopes).

## The three 403s

| | Cause | Who fixes it | Retry? |
|---|---|---|---|
| `InsufficientScopeError` | Scope never granted | **You** — re-run consent with the scope | No |
| `DataAccessError` (40303, 40305) | Login cannot see this debtor/company | **The customer's Nmbrs admin** | No |
| `SubscriptionError` (40304) | Environment disabled, no valid subscription | **The customer**, with Nmbrs | No |

None are retryable. All three are permanent until someone acts.

## Retry policy

| Exception | Retry | Strategy | Why |
|---|---|---|---|
| `NmbrsTimeoutError`, `NmbrsConnectionError` | Yes, GET only | 3 attempts, exponential + jitter | Transient. **Never retry non-idempotent writes** — a timeout does not mean the write failed |
| `InvalidTokenError` (401) | Once | Refresh, replay once | A second 401 after refresh is not an expiry problem |
| `PermissionError` and subclasses (403) | No | — | Permanent until configuration changes |
| `NotFoundError` (404) | No | — | The resource will not appear by retrying |
| `ValidationError`, `InvalidRequestError` (400) | No | — | The request is wrong; sending it again keeps it wrong |
| `RateLimitError` (42908) | Yes | 5 attempts, exponential + jitter, honours `Retry-After` if present | Short-term throttle |
| `QuotaExceededError` (42909) | **No** | — | Plan volume exhausted; resets on a billing cycle, not in seconds |
| `ServerError` 502, 503 | Yes | 3 attempts, exponential + jitter | Usually a deploy or gateway blip |
| `ServerError` 500 | No | — | A real Nmbrs-side bug |

Nmbrs documents **no numeric rate limit** and no `X-RateLimit-*` headers, and none appear
anywhere in the OpenAPI spec. The SDK honours `Retry-After` **if the response carries it**
and otherwise falls back to exponential backoff. Do not build against a specific limit.

Jitter is not decoration: without it, a fleet of workers throttled together retries in
lockstep and throttles itself again.

## Identity-server errors are not API errors

Failures from `identityservice.nmbrs.com` use the RFC 6749 shape
(`{"error": "invalid_grant", ...}`), not RFC 7807. They surface as `IdentityServerError`,
which is **not** a subclass of `APIError`.

| `error` | SDK exception | Fix |
|---|---|---|
| `invalid_grant` | `InvalidGrantError` → often `ReauthorizationRequired` | Refresh token expired, used, or consent revoked. Check for a newer token in the store first |
| `invalid_client` | `InvalidClientError` | Wrong credentials, or Basic header not percent-encoded per RFC 6749 §2.3.1 |
| `invalid_scope` | `IdentityServerError` | Scope does not exist or is not enabled for your client |
| `invalid_request` | `IdentityServerError` | Malformed request, or an expired PAR `request_uri` |
| `unauthorized_client` | `IdentityServerError` | Grant type not permitted — Nmbrs supports authorization code only |
| `access_denied` | `IdentityServerError` | User declined consent. Not an error to alert on |
| `server_error`, `temporarily_unavailable` | `IdentityServerError` | Retry with backoff |

Full detail in [authentication.md](./authentication.md#identity-server-errors).

## Errors with no HTTP status

| Exception | Trigger | Fix |
|---|---|---|
| `NmbrsConfigError` | Missing subscription key, no token and no store, unusable store path | Fail-fast at construction. Fix the setup |
| `NmbrsTimeoutError` | Connect or read timeout | Retry GETs. For writes, verify state before retrying |
| `NmbrsConnectionError` | DNS, TLS, connection reset, proxy failure | Check network and proxy configuration |
| `TokenStoreError` | Store load/save/delete failed | Check permissions and disk. A failed `save()` after a refresh is critical — the rotated token may be lost |
| `ReauthorizationRequired` | The grant is terminally dead | Send the customer through consent again. Carries `.token_key` so you know which one |
| `EmployeeResolutionError` | `api.employee(id)` could not find an owning company | The employee is not in any company this token can see, or the id is wrong. Pass `company_id=` explicitly to skip resolution |

The subscription key is validated **locally** before the first request. A missing key
otherwise produces a confusing 401 that looks like a token problem.

## Failure modes

The table to reach for when something is broken and the exception alone is not enough.

| Symptom | Likely cause | Exception | Remedy |
|---|---|---|---|
| Every call 401s from the very first request | Subscription key missing or wrong | `NmbrsConfigError` / `MissingTokenError` | Check `X-Subscription-Key`; it is separate from OAuth |
| Worked yesterday, all calls now 401 | Refresh token expired after 30 days idle | `ReauthorizationRequired` | Re-consent. Refresh on a schedule, not only on demand |
| 401s under load, fine when serial | Concurrent refresh burned the single-use token | `InvalidGrantError` | Serialise refresh — see [concurrency](./authentication.md#concurrency-and-crash-safety) |
| Refresh fails right after a deploy | Client secret rotated | `InvalidClientError` | Update config; existing refresh tokens still work |
| No refresh token at all | `offline_access` not requested | `NmbrsConfigError` | Re-consent including `offline_access` |
| 403 on one endpoint, others fine | Scope not granted | `InsufficientScopeError` | Re-consent with the named scope |
| 403 on every endpoint for one customer | Login cannot see that debtor/company | `DataAccessError` | Their Nmbrs admin reviews access rights |
| 403 on all endpoints, all customers | Environment disabled | `SubscriptionError` | Customer contacts Nmbrs |
| Works for tenant A, 403 for tenant B | Used A's token against B's company | `DataAccessError` | Check your `token_key` routing |
| 400 on a list call | `pageSize` above the maximum of 100 | `ValidationError` | Cap at 100 |
| Empty `data` on a single-item read | Resource does not exist | `ResourceNotFoundError` | Verify the id |
| Duplicate or missing rows across pages | Data changed while paginating | none | Nmbrs offers no snapshot. Use `createdFrom`/`changedFrom` where available |
| `api.employee(id)` is very slow the first time | Company resolution scanning all visible companies | none | Use `api.company(cid).employee(id)`, or `api.prime(company_id)` |
| `EmployeeResolutionError` on a known employee | Employee outside this token's visible companies, or moved company | `EmployeeResolutionError` | Pass `company_id=` explicitly |
| Parse error instead of a clean error object | Gateway returned HTML on 502/503 | `ServerError` | Already handled; report if you see a raw parse error |
| Retries make throttling worse | No jitter, fleet retrying in lockstep | `RateLimitError` | Use the SDK's backoff rather than your own loop |
| Backoff never recovers | Quota exhausted, not throttled | `QuotaExceededError` | Check the code: 42909 is not retryable |
| Token refreshes constantly | Local clock badly skewed | none | Sync the system clock; expiry is computed in UTC |
| New Nmbrs field appears, code breaks | Model rejecting unknown fields | `pydantic.ValidationError` | Should not happen — models use `extra="allow"`. Report it |
| Document endpoint returns 202 | Async document generation | none | Poll `GET /api/documents/{taskId}` |

## Handling patterns

Catch the specific thing you can act on, and let the rest surface:

```python
from nmbrs_rest.errors import (
    DataAccessError,
    InsufficientScopeError,
    QuotaExceededError,
    ReauthorizationRequired,
    SubscriptionError,
)

try:
    for employee in company.employees():
        process(employee)

except ReauthorizationRequired as exc:
    # Actionable by the customer: send them back through consent.
    notify_reconnect(exc.token_key)

except InsufficientScopeError as exc:
    # Actionable by you: a scope is missing from your consent request.
    logger.error("missing scope %s for %s", sorted(exc.missing), exc.path)
    raise

except (DataAccessError, SubscriptionError) as exc:
    # Actionable by the customer's Nmbrs administrator. Not a bug; do not page anyone.
    mark_tenant_blocked(tenant_id, reason=str(exc))

except QuotaExceededError:
    # Retrying is futile. Stop the run and alert.
    alert_ops("Nmbrs API quota exhausted")
    raise
```

Retries, refresh and backoff are handled inside the SDK. A `try/except` that catches
`RateLimitError` and sleeps is duplicating work already done and usually makes throttling
worse.

### What to alert on

| Alert | Do not alert |
|---|---|
| `QuotaExceededError` — everything stops | `DataAccessError` — customer configuration |
| `ServerError` 500 sustained | `SubscriptionError` — customer billing |
| `TokenStoreError` — you may be losing tokens | `access_denied` — user declined consent |
| `InsufficientScopeError` — your bug | `RateLimitError` — handled internally |
| `ReauthorizationRequired` spiking across tenants | A single `ReauthorizationRequired` |

### Logging

```python
logger.warning(
    "nmbrs call failed: %s %s -> %s/%s",
    exc.method, exc.path, exc.http_status, exc.code,
)
```

Exception fields are safe to log — tokens are redacted at construction. `httpx` debug
logging is **not** safe: it dumps `Authorization` and `X-Subscription-Key` headers verbatim.
Do not enable it in production.

### Reducing request volume

The company-scoped design means naive per-employee access is expensive: reading
`.contracts` for 200 employees individually is 200 requests against the same underlying
company endpoint. Prefer the bulk path, which fetches once and populates every employee:

```python
company.prefetch("contracts")            # one paginated pass
for employee in company.employees():
    employee.contracts                   # served from cache, no request
```
