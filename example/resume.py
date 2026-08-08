"""Every run after the first: no browser, straight to the data.

    python resume.py

main.py needs a human at a consent screen. This does not: it hands the saved
refresh token to the client and the SDK mints a fresh access token on the first
request. This is what a scheduled job or a backend service actually looks like.

Refresh tokens rotate - Nmbrs kills the old one every time it issues a new one -
so `on_token_refresh` writes the new value back to .env as it arrives. Skip that
and the next run is locked out.
"""

from global_variables import (
    client_id,
    client_secret,
    refresh_token,
    save_refresh_token,
    subscription_key,
)
from nmbrs_rest import Nmbrs
from nmbrs_rest.errors import NmbrsError, ReauthorizationRequired

if not refresh_token:
    raise SystemExit("No NMBRS_REFRESH_TOKEN in .env yet. Run `python main.py` first.")

with Nmbrs(
    client_id,
    client_secret,
    subscription_key,
    refresh_token=refresh_token,
    on_token_refresh=save_refresh_token,
) as api:
    try:
        companies = api.companies()
    except ReauthorizationRequired as exc:
        # The refresh token is 30 days old, was already used, or the customer
        # revoked consent. Nothing to do but send them through main.py again.
        raise SystemExit(f"Consent is gone, re-run main.py: {exc}") from exc
    except NmbrsError as exc:
        raise SystemExit(f"{type(exc).__name__}: {exc}") from exc

    print(f"{len(companies)} companies\n")
    for company in companies:
        print(f"{company.id}  {company.name}")

    # The token that just got minted is already saved; this is only to show that
    # the properties are live rather than snapshots of what was passed in.
    print(f"\nRefresh token now ends ...{(api.refresh_token or '')[-6:]}")
