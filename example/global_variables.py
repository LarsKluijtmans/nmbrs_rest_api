"""Configuration shared by every script here.

Nothing secret lives in this file: it only reads .env, so the credentials stay in
one place that is easy to keep out of version control.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from nmbrs_rest import ALL_READ_SCOPES
from nmbrs_rest.tokens import Token

#: Next to this file, not next to whatever directory you happen to run from.
ENV_PATH = Path(__file__).with_name(".env")
TEMPLATE_PATH = Path(__file__).with_name(".env.example")
REFRESH_TOKEN_KEY = "NMBRS_REFRESH_TOKEN"

# Copies .env into os.environ. Real environment variables win over the file, so
# you can override any of these for one run without editing anything.
load_dotenv(ENV_PATH)


def _required(name: str) -> str:
    """Read a setting, or explain what is missing instead of raising KeyError."""
    value = os.environ.get(name, "").strip()
    if value:
        return value

    if not ENV_PATH.exists():
        sys.exit(
            f"No {ENV_PATH.name} found in {ENV_PATH.parent}.\n\n"
            f"    cp {TEMPLATE_PATH.name} {ENV_PATH.name}\n\n"
            "then fill it in with your credentials from developer.nmbrs.com."
        )
    sys.exit(
        f"{name} is not set in {ENV_PATH}.\n\n"
        "Get client id and secret from your OAuth application at developer.nmbrs.com,\n"
        "and the subscription key by subscribing to a product there. The redirect URI\n"
        "must be registered on that same application."
    )


# Your OAuth application, from developer.nmbrs.com.
client_id = _required("NMBRS_CLIENT_ID")
client_secret = _required("NMBRS_CLIENT_SECRET")

# A separate credential from OAuth, created by subscribing to a product. It goes
# on every API call as X-Subscription-Key and is not part of the token flow.
subscription_key = _required("NMBRS_SUBSCRIPTION_KEY")

# Must match a redirect URI registered on the application exactly, and must be
# the same string at consent time and at token-exchange time.
redirect_uri = _required("NMBRS_REDIRECT_URI")

# Filled in by save_refresh_token() below; empty until you have logged in once.
refresh_token = os.environ.get(REFRESH_TOKEN_KEY, "").strip() or None

# Every scope the API defines on a GET, plus offline_access - without which no
# refresh token is issued and the whole thing stops working in an hour. Sorted
# so the consent URL is identical from run to run.
#
# This is the "one-off script" setting. A real integration should list the few
# scopes it actually uses: asking a customer to approve sixteen of them, or any
# write scope it will never call, is a bad look on the consent screen.
scopes = sorted(ALL_READ_SCOPES)


def save_refresh_token(token: Token) -> None:
    """Write the current refresh token back to .env.

    Pass this as ``on_token_refresh``. Refresh tokens rotate: Nmbrs kills the old
    one every time it issues a new one, so a value you store once goes stale the
    moment the SDK refreshes in the background. This keeps .env in step.

    Only the one line is touched; the rest of the file is left as it is.
    """
    value = token.refresh_token or ""

    # .env need not exist - the settings above accept real environment variables
    # too. Refusing to write here would throw away a rotated token, which is
    # unrecoverable without sending the user back through consent.
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []

    for index, line in enumerate(lines):
        if line.startswith(f"{REFRESH_TOKEN_KEY}="):
            lines[index] = f"{REFRESH_TOKEN_KEY}={value}"
            break
    else:
        lines.append(f"{REFRESH_TOKEN_KEY}={value}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[REFRESH_TOKEN_KEY] = value
