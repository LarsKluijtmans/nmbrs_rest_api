"""First run: consent, callback, tokens, first API call.

    python main.py

Nmbrs supports the authorization code flow only, so the first token always needs a
human to approve in a browser. The awkward part is the redirect: Nmbrs sends the
browser to NMBRS_REDIRECT_URI with the authorization code on the query string, and
if nothing is listening there you end up copying the code out of the address bar
before it expires.

So this starts a throwaway HTTP server on that port and lets the browser deliver
the code to it. Doing consent and exchange in one process also means the `state`
parameter can be verified, which is the CSRF check.

Run this once. After that the refresh token in .env is enough - see resume.py,
which does the same work with no browser involved.

Requires NMBRS_REDIRECT_URI to be a loopback address (http://localhost:4000 works)
that is also registered on the application at developer.nmbrs.com.
"""

import webbrowser

from callback import wait_for_callback
from global_variables import (
    client_id,
    client_secret,
    redirect_uri,
    save_refresh_token,
    scopes,
    subscription_key,
)
from nmbrs_rest import Nmbrs

# redirect_uri goes on the client because both halves of the flow need it:
# the consent URL sends the user there, and the token exchange has to quote
# the same value back. on_token_refresh writes every token to .env, starting
# with the one authenticate() returns.
with Nmbrs(
    client_id,
    client_secret,
    subscription_key,
    redirect_uri=redirect_uri,
    on_token_refresh=save_refresh_token,
) as api:
    # 1. Consent. login() picks a random state and remembers it on `api`.
    url = api.login(scopes=scopes)
    print(f"Approve the app in your browser:\n\n{url}\n")
    webbrowser.open(url)

    # 2. Catch the redirect instead of reading it off the address bar.
    print(f"Listening on {redirect_uri} for the redirect ...")
    callback = wait_for_callback(redirect_uri)
    if "error" in callback:
        description = callback.get("error_description", "no description")
        raise SystemExit(f"Nmbrs refused the authorization: {callback['error']} ({description})")

    # 3. Exchange. Handing `state` back makes the SDK compare it with the one
    #    it issued - the CSRF check the numbered scripts have to skip.
    api.authenticate(callback["code"], state=callback.get("state"))
    print(f"Authenticated with {len(api.scopes)} scopes. Refresh token saved to .env.\n")

    # 4. From here on it is ordinary API use. The SDK refreshes on its own
    #    when the access token expires.
    for debtor in api.debtors():
        print(f"debtor: {debtor.id}, name: {debtor.name}, number: {debtor.number}")
        for company in debtor.companies():
            print(f"  company: {company.id}, name: {company.name}, number: {company.number}")
            employees = company.employees()
            print(f"    {len(employees)} employees")
