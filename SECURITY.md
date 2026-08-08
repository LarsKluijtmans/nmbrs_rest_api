# Security Policy

## Reporting a vulnerability

**Do not open a public issue.**

Report privately through GitHub:
[Security → Report a vulnerability](https://github.com/LarsKluijtmans/nmbrs_rest_api/security/advisories/new).

If that is unavailable, email <info@lk-software.com> with `SECURITY` in the subject.

Please include what the issue is, how to reproduce it, and what an attacker could achieve.

You can expect an acknowledgement within **5 working days** and an assessment within
**15 working days**. This is a small project — that is a genuine estimate, not an SLA.
Please give a reasonable window for a fix before public disclosure.

### What belongs elsewhere

- **Vulnerabilities in the Nmbrs API or platform itself** go to Nmbrs, not here:
  <https://www.nmbrs.com/> / <https://support.nmbrs.com/>.
- **A leaked credential of your own** — rotate it in the
  [Nmbrs Developer Portal](https://developer.nmbrs.com/) and revoke the consent from the
  App Manager in your Nmbrs environment. Nothing needs reporting here.

## Supported versions

While pre-1.0, only the latest released version receives fixes. After 1.0, the latest minor
of the current major.

## Security model

This SDK holds credentials that grant access to payroll and HR data — among the most
sensitive data an organisation has. Be clear about what the SDK does and does not do.

### What the SDK handles

- **Tokens are never logged.** Access tokens, refresh tokens, client secrets and
  subscription keys are redacted in exception messages, `repr()` output and debug logging.
- **Rotation is handled safely.** Nmbrs refresh tokens are single-use. The SDK persists a
  rotated token before using it, and serialises concurrent refreshes so two workers cannot
  burn the same token.
- **TLS is enforced** by httpx defaults. Certificate verification is not disabled, and
  there is no option to disable it.

### What the SDK does not do

- **`FileTokenStore` does not encrypt anything.** It writes JSON with restrictive
  permissions (`0600` on POSIX). That protects against other *users* on the same machine.
  It does **not** protect against: anyone who can read the process's files, a stolen disk
  or backup, a container image with the file baked in, or a compromised host. If you need
  encryption at rest, use `KeyringTokenStore` or implement the `TokenStore` protocol
  against your own secret manager.
- **The SDK does not choose where your secrets live.** Client secrets and subscription keys
  are passed in by you. Sourcing them from a secret manager rather than a file or an
  environment variable is your call and your responsibility.
- **The SDK cannot limit what a token can reach.** Scope is fixed at consent time. Request
  the narrowest set your integration needs — read-only scopes (`*.read`) where you only
  read. See [docs/authentication.md](docs/authentication.md).

### If you use this SDK

- Never commit token store files. Add them to `.gitignore`.
- Never commit `client_secret` or `X-Subscription-Key` values.
- Use separate `client_id`s for development and production.
- Treat a refresh token as equivalent to a 30-day password for the consented Nmbrs data.
- Revoke consent when an integration is decommissioned — do not just delete the token file.
- Restrict who can read the machine or container running the integration.

## Dependencies

Runtime dependencies are deliberately few: `httpx` and `pydantic`. Dependabot watches both
these and the GitHub Actions used in CI and releases.
