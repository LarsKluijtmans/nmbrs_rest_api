# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) — with the
pre-1.0 caveats described in [docs/releasing.md](docs/releasing.md#version-numbering).

Release notes on GitHub are generated from commit history; this file is the curated,
human-written record. Update it before tagging.

## [Unreleased]

Nothing yet.

## [0.0.1] - 2026-08-08

### Added

- **`Nmbrs` facade.** `Nmbrs(client_id, client_secret, subscription_key)` owns the whole
  lifecycle: `login(redirect_uri, scopes)` returns the consent URL, `authenticate(code)`
  exchanges it, and `access_token` / `refresh_token` / `scopes` / `expires_at` are live
  properties rather than snapshots. `refresh()` forces a refresh, `logout()` revokes.
  Construct with `refresh_token=` to resume without a browser, and `on_token_refresh=`
  to be told about rotation instead of polling for it.
- **Resource layer.** `api.debtors()`, `api.companies()`, `api.employees(company_id)` and
  `api.employee(company_id, employee_id)` return `Debtor` / `Company` / `Employee`
  objects. Collections are eager; `Page` remains available for streaming.
- **60 generated read methods** across the three resources, from
  `tools/generate_resources.py` (`--check` in CI). Reads are methods rather than
  attributes because 33 of the 38 employee endpoints take a `year`, `period` or
  `created_from` filter, which an attribute cannot express. Results are cached per
  object *and per argument set*, so `contracts()` twice is one request while
  `contracts(created_from=...)` is its own question.
- The SDK now unwraps the per-employee response wrapper. Employee reads arrive as
  `{"employeeId": ..., "<payloadKey>": ...}` with a key that differs per endpoint
  (`contracts`, `info`, `EmployeeLeaveRequests`); callers get the payload. The three
  endpoints that ignore `employeeId` — `privateInfos`, `extraFields`, `useraccounts` —
  are filtered client-side.
- **Core runtime.** `errors` (full exception hierarchy and RFC 7807 mapping), `tokens`
  (`Token`, `TokenStore` protocol, memory/file/keyring/callback stores), `auth` (OAuth
  authorization code flow with PAR and PKCE), `transport` (auth injection, refresh-on-401
  with replay, retry policy) and `pagination` (lazy auto-paginating `Page`).
- **Scope-aware 403 diagnosis.** `_scopes.py` is generated from the vendored OpenAPI spec,
  so a 403 names the exact scope missing for the exact operation.
- Vendored OpenAPI spec plus `tools/fetch_spec.py` and `tools/generate_scopes.py`, both
  with `--check` modes wired into CI.
- Project design: architecture, the resource model and the generation strategy
  (`DESIGN.md`).
- Authentication contract: OAuth 2.0 authorization code flow, PAR, token persistence and
  rotation handling (`docs/authentication.md`).
- Error contract: full exception hierarchy and scope-aware 403 diagnosis
  (`docs/errors.md`).
- Packaging, CI, and the TestPyPI/PyPI release pipeline (`docs/releasing.md`).
- `scripts/try_testpypi.py` installs the staged package from TestPyPI into a throwaway
  virtualenv and runs `scripts/verify_install.py` against it, so a staging release is
  verified as an installed artifact rather than as a working directory.
- `scripts/login.py` runs the authorization code flow end to end: opens the browser,
  catches the redirect on localhost, exchanges the code, and writes the tokens where a
  `FileTokenStore` can find them. With `--subscription-key` it then makes a real
  `GET /api/companies` call to confirm the credentials work.
- `unwrap_one` is exported from the package root alongside `Page`. Both are needed for
  ordinary reads, so exporting only one of them was an oversight.

### Changed

- **`api.employee()` now requires both ids**: `api.employee(company_id, employee_id)`.
  The earlier design resolved the owning company by scanning every visible company,
  because Nmbrs exposes no employee-to-company lookup. That made one innocuous-looking
  call cost up to one request per company, with a cost depending on consent breadth and
  on listing order. Requiring the company id costs one request, always.
- README and `DESIGN.md` rewritten around the implemented API. The status note
  previously claimed the package "gets you a version number and nothing else", then that
  `Nmbrs` did not exist; both are now false.

### Removed

- `EmployeeResolutionError`, which only existed for the company-scanning path. A wrong
  or foreign employee id now raises `ResourceNotFoundError` naming both ids.
  `NotAuthenticatedError` takes its place in the hierarchy, raised when a read is
  attempted before any token exists.

### Notes

- Reads return `dict[str, Any]`. Typed pydantic models are the next step.
- Writes (39 POST/PUT/DELETE operations), `PayrollRun`, and the standalone reads
  (`countries`, `user_info`, `subscription`, `document`, `salary_table`,
  `end_contract_reasons`) are not implemented.

[Unreleased]: https://github.com/LarsKluijtmans/nmbrs_rest_api/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/LarsKluijtmans/nmbrs_rest_api/releases/tag/v0.0.1
