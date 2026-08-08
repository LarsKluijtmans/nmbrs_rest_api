# Example project

A small, runnable project showing how to use
[`nmbrs-rest-api`](https://pypi.org/project/nmbrs-rest-api/) end to end: get consent
once in a browser, then run headless from a saved refresh token.

| File | What it is |
| --- | --- |
| `main.py` | **Run this first.** Consent in the browser, exchange the code, save the refresh token. |
| `resume.py` | Every run after that. No browser — this is what a cron job or backend service looks like. |
| `explore.py` | A tour of the read API: filters, caching, errors worth catching, raw access. |
| `global_variables.py` | Config and credentials, read from `.env`. |
| `callback.py` | A tiny HTTP server that catches the OAuth redirect. |

## Setup

**1. Install**

```bash
python -m venv venv
venv/Scripts/activate          # Windows
source venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
```

**2. Get credentials** from [developer.nmbrs.com](https://developer.nmbrs.com/):

- An **OAuth application** → client id and client secret.
- A **subscription key**, by subscribing to a product. This is a separate credential
  from OAuth and goes on every request as `X-Subscription-Key`.
- A **redirect URI** registered on that application. `http://localhost:4000` works for
  local use; you get up to 5 per application.

**3. Configure**

```bash
cp .env.example .env
```

Fill in the four values. `NMBRS_REFRESH_TOKEN` stays empty — `main.py` writes it.

> `.env` holds a live refresh token once you have logged in. It is the equivalent of a
> password and is already in `.gitignore`. Never commit it.

## Run

```bash
python main.py      # once: opens the browser, saves the refresh token
python resume.py    # thereafter: no browser
python explore.py   # a tour of what you can read
```

`main.py` prints a URL, opens it, and waits. Approve the app, and the browser is
redirected back to `callback.py`, which hands the authorization code to the SDK. Nmbrs
supports only the authorization code flow, so this browser step is unavoidable for the
first token — but only for the first.

## Things worth noticing

**Refresh tokens rotate.** Nmbrs kills the old refresh token every time it issues a new
one, and they last 30 days. `save_refresh_token` is passed as `on_token_refresh`, so
every new token is written to `.env` as it arrives. Skip that and the next run is locked
out. This is the single most common way a Nmbrs integration dies overnight.

**The example asks for every read scope.** `global_variables.py` uses `ALL_READ_SCOPES`
so all of `explore.py` works. A real integration should list only the scopes it actually
uses — asking a customer to approve sixteen of them looks bad on the consent screen, and
a 403 will tell you exactly which one you are missing if you get it wrong.

**Reads are methods, and they cache.** `employee.contracts()` twice is one request;
`employee.contracts(created_from=...)` is a different question and gets its own entry.
`explore.py` demonstrates both.

**Both ids are needed for an employee.** `api.employee(company_id, employee_id)` — Nmbrs
exposes no employee-to-company lookup, so an employee id alone is not enough.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `No .env found` | `cp .env.example .env` and fill it in. |
| `NMBRS_CLIENT_ID is not set` | The value is blank in `.env`. |
| `Cannot listen on http://localhost:4000` | Something else has the port, or the URI is not a loopback address. |
| `No redirect ... within 300s` | The consent screen was never completed, or the redirect URI is not registered on the application. |
| `invalid_grant` on the token exchange | The code expired (5 minutes, single use), or the redirect URI does not match exactly. |
| `ReauthorizationRequired` | The refresh token expired, was already used, or consent was revoked. Run `main.py` again. |
| `InsufficientScopeError` | The message names the exact scope. Re-consent including it — scope cannot be widened for an existing token. |

Full error reference:
[docs/errors.md](https://github.com/LarsKluijtmans/nmbrs_rest_api/blob/main/docs/errors.md).

## Found a bug?

Please [open an issue](https://github.com/LarsKluijtmans/nmbrs_rest_api/issues/new) —
include what you called, what happened, and the exception (they are safe to paste;
tokens are redacted before the message is built).
