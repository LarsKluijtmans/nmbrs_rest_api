# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) — with the
pre-1.0 caveats described in [docs/releasing.md](docs/releasing.md#version-numbering).

Release notes on GitHub are generated from commit history; this file is the curated,
human-written record. Update it before tagging.

## [Unreleased]

### Added

- **Core runtime.** `errors` (full exception hierarchy and RFC 7807 mapping), `tokens`
  (`Token`, `TokenStore` protocol, memory/file/keyring/callback stores), `auth` (OAuth
  authorization code flow with PAR and PKCE), `transport` (auth injection, refresh-on-401
  with replay, retry policy) and `pagination` (lazy auto-paginating `Page`).
- **Scope-aware 403 diagnosis.** `_scopes.py` is generated from the vendored OpenAPI spec,
  so a 403 names the exact scope missing for the exact operation.
- Vendored OpenAPI spec plus `tools/fetch_spec.py` and `tools/generate_scopes.py`, both
  with `--check` modes wired into CI.
- Project design: architecture, lazy-loading resource model and company resolution strategy
  (`DESIGN.md`).
- Authentication contract: OAuth 2.0 authorization code flow, PAR, token persistence and
  rotation handling (`docs/authentication.md`).
- Error contract: full exception hierarchy and scope-aware 403 diagnosis
  (`docs/errors.md`).
- Packaging, CI, and the TestPyPI/PyPI release pipeline (`docs/releasing.md`).
- `scripts/try_testpypi.py` installs the staged package from TestPyPI into a throwaway
  virtualenv and runs `scripts/verify_install.py` against it, so a staging release is
  verified as an installed artifact rather than as a working directory.

### Notes

- The `Nmbrs` facade and the debtor/company/employee resource layer are not implemented
  yet, so there is no end-to-end read path. `Transport` is usable directly.

[Unreleased]: https://github.com/LarsKluijtmans/nmbrs_rest_api/commits/main
