#!/usr/bin/env python3
"""Get a first set of Nmbrs tokens by running the authorization code flow.

    python scripts/login.py --client-id ... --client-secret ... --subscription-key ...

Opens your browser, catches the redirect on localhost, exchanges the code, and
writes the tokens to a file a ``FileTokenStore`` can read. With
``--subscription-key`` it then makes a real call to prove the whole chain works.

Credentials can come from the environment instead of the command line, which keeps
them out of your shell history::

    NMBRS_CLIENT_ID  NMBRS_CLIENT_SECRET  NMBRS_SUBSCRIPTION_KEY

Before this can work, the redirect URI below must be registered on your client in
the Nmbrs portal (up to 5 per client). ``http://localhost:8080/callback`` is fine
for local use; see docs/authentication.md.

The token file holds a live refresh token and is equivalent to a password. It is
written with owner-only permissions where the OS supports it, and the default name
is gitignored.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

from nmbrs_rest import FileTokenStore, OAuth, Token
from nmbrs_rest.errors import NmbrsError

DEFAULT_REDIRECT = "http://localhost:8080/callback"
DEFAULT_TOKEN_FILE = ".nmbrs-tokens.json"

# A read-only starter set. `offline_access` is not optional: without it the
# identity server returns no refresh token and the integration dies after an hour.
DEFAULT_SCOPES = [
    "offline_access",
    "company.info.read",
    "employee.info.read",
    "employee.employment.read",
]

_PAGE = """<!doctype html><meta charset="utf-8"><title>{title}</title>
<body style="font:16px system-ui;max-width:34rem;margin:4rem auto;padding:0 1rem">
<h1 style="font-size:1.3rem">{title}</h1><p>{body}</p></body>"""


class _Callback(BaseHTTPRequestHandler):
    """Single-shot handler that captures the query string off the redirect."""

    captured: ClassVar[dict[str, list[str]]] = {}

    def do_GET(self) -> None:
        query = parse_qs(urlparse(self.path).query)

        if "code" not in query and "error" not in query:
            # Browsers ask for /favicon.ico and friends. Ignore anything that is
            # not the redirect itself, or we stop listening too early.
            self.send_response(404)
            self.end_headers()
            return

        _Callback.captured = query
        if "error" in query:
            title = "Authorization failed"
            body = f"{query['error'][0]}: {query.get('error_description', [''])[0]}"
        else:
            title = "Authorized"
            body = "You can close this tab and go back to the terminal."

        page = _PAGE.format(title=title, body=body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *_: Any) -> None:
        """Silence the default stderr access log."""


def wait_for_redirect(redirect_uri: str, timeout: float) -> dict[str, list[str]]:
    parsed = urlparse(redirect_uri)
    host, port = parsed.hostname or "localhost", parsed.port or 80

    _Callback.captured = {}
    try:
        server = HTTPServer((host, port), _Callback)
    except OSError as exc:
        sys.exit(f"cannot listen on {host}:{port} ({exc}). Is something already using it?")

    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True
    )
    thread.start()

    # serve_forever runs on the thread; poll here so Ctrl-C still works and so a
    # stray /favicon.ico request does not end the wait.
    tick = threading.Event()
    try:
        waited = 0.0
        while not _Callback.captured and waited < timeout:
            tick.wait(0.2)
            waited += 0.2
    finally:
        server.shutdown()
        server.server_close()

    if not _Callback.captured:
        sys.exit(f"timed out after {timeout:.0f}s waiting for the redirect")
    return _Callback.captured


def describe(token: Token) -> str:
    scopes = " ".join(sorted(token.scopes)) or "(none reported)"
    refresh = "yes" if token.refresh_token else "NO - you omitted offline_access"
    return (
        f"  expires_at    {token.expires_at:%Y-%m-%d %H:%M:%S %Z}\n"
        f"  refresh token {refresh}\n"
        f"  scopes        {scopes}"
    )


def smoke_test(token: Token, subscription_key: str, oauth: OAuth, store: FileTokenStore) -> int:
    from nmbrs_rest import Transport
    from nmbrs_rest.pagination import Page

    print("\n==> calling GET /api/companies with the new token")
    transport = Transport(
        subscription_key=subscription_key,
        oauth=oauth,
        token_store=store,
    )
    try:
        companies = list(Page(transport, "/api/companies", factory=lambda row: row, page_size=100))
    except NmbrsError as exc:
        print(f"    FAILED: {type(exc).__name__}: {exc}")
        return 1

    print(f"    {len(companies)} companies visible to this token")
    for company in companies[:10]:
        print(f"      {company.get('companyId', '?')}  {company.get('name', '')}")
    if len(companies) > 10:
        print(f"      ... and {len(companies) - 10} more")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--client-id", default=os.environ.get("NMBRS_CLIENT_ID"))
    parser.add_argument("--client-secret", default=os.environ.get("NMBRS_CLIENT_SECRET"))
    parser.add_argument(
        "--subscription-key",
        default=os.environ.get("NMBRS_SUBSCRIPTION_KEY"),
        help="if given, make a real API call afterwards to prove the token works",
    )
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT)
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        metavar="SCOPE",
        help=f"repeatable; default: {' '.join(DEFAULT_SCOPES)}",
    )
    parser.add_argument("--token-file", default=DEFAULT_TOKEN_FILE, type=Path)
    parser.add_argument("--token-key", default="default")
    parser.add_argument("--pkce", action="store_true", help="use PKCE S256 (undocumented by Nmbrs)")
    parser.add_argument("--no-browser", action="store_true", help="print the URL, do not open it")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    missing = [
        flag
        for flag, value in (
            ("--client-id", args.client_id),
            ("--client-secret", args.client_secret),
        )
        if not value
    ]
    if missing:
        parser.error(
            f"{', '.join(missing)} required (or set NMBRS_CLIENT_ID / NMBRS_CLIENT_SECRET)"
        )

    scopes = args.scopes or DEFAULT_SCOPES
    if "offline_access" not in scopes:
        print("!!  offline_access is not in your scopes; you will get no refresh token")

    oauth = OAuth(
        client_id=args.client_id,
        client_secret=args.client_secret,
        redirect_uri=args.redirect_uri,
    )
    request = oauth.authorization_url(scopes, pkce=args.pkce)

    print(f"==> redirect URI  {args.redirect_uri}")
    print(f"==> scopes        {' '.join(scopes)}")
    print("\nOpen this and approve:\n")
    print(f"    {request.url}\n")
    if not args.no_browser:
        webbrowser.open(request.url)

    print(f"==> listening for the redirect (up to {args.timeout:.0f}s)")
    query = wait_for_redirect(args.redirect_uri, args.timeout)

    if "error" in query:
        description = query.get("error_description", [""])[0]
        sys.exit(f"authorization denied: {query['error'][0]} {description}".rstrip())

    print("==> exchanging the code for tokens")
    try:
        token = oauth.exchange_code(
            query["code"][0],
            code_verifier=request.code_verifier,
            returned_state=query.get("state", [None])[0],
            expected_state=request.state,
        )
    except NmbrsError as exc:
        sys.exit(f"exchange failed: {type(exc).__name__}: {exc}")

    store = FileTokenStore(args.token_file)
    store.save(args.token_key, token)

    print(f"\n==> saved to {args.token_file}  (key: {args.token_key!r})")
    print(describe(token))
    print("\n    This file contains a live refresh token. Treat it as a password.")

    exit_code = 0
    if args.subscription_key:
        exit_code = smoke_test(token, args.subscription_key, oauth, store)

    print(
        f"\nUse it:\n"
        f"    from nmbrs_rest import FileTokenStore, OAuth, Transport\n"
        f"    store = FileTokenStore({str(args.token_file)!r})\n"
        f"    oauth = OAuth(client_id=..., client_secret=...)\n"
        f"    api = Transport(subscription_key=..., oauth=oauth, token_store=store)\n"
        f"    api.get_json('/api/companies')\n"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
