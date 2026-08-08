import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

#: How long to wait at the consent screen before giving up, in seconds.
CALLBACK_TIMEOUT = 300

_PAGE = """<!doctype html>
<meta charset="utf-8"><title>Nmbrs</title>
<body style="font: 1rem system-ui; margin: 4rem auto; max-width: 30rem">
<h1>{heading}</h1><p>{message}</p>
"""


class _CallbackHandler(BaseHTTPRequestHandler):
    """Answers the one request Nmbrs redirects the browser to."""

    # Class attributes rather than instance ones: BaseHTTPRequestHandler builds a
    # new instance per request, so there is nowhere else to put the result.
    params: ClassVar[dict[str, str]] = {}
    received = threading.Event()

    def do_GET(self) -> None:
        query = {key: values[0] for key, values in parse_qs(urlparse(self.path).query).items()}

        # Browsers ask for /favicon.ico and friends unprompted. Only the request
        # carrying the code (or an error) ends the wait.
        if "code" not in query and "error" not in query:
            self.send_response(204)
            self.end_headers()
            return

        _CallbackHandler.params = query
        if "code" in query:
            self._respond("Authorized", "You can close this tab and go back to the terminal.")
        else:
            self._respond("Authorization failed", query.get("error", "unknown error"))
        _CallbackHandler.received.set()

    def _respond(self, heading: str, message: str) -> None:
        body = _PAGE.format(heading=heading, message=message).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Drop the default request logging so it does not mix into our output."""


def wait_for_callback(uri: str, timeout: float = CALLBACK_TIMEOUT) -> dict[str, str]:
    """Serve the host and port of `uri` until the redirect lands, then return its query."""
    parsed = urlparse(uri)
    try:
        server = HTTPServer((parsed.hostname or "localhost", parsed.port or 80), _CallbackHandler)
    except OSError as exc:
        raise SystemExit(f"Cannot listen on {uri}: {exc}") from exc

    # serve_forever() blocks, so it runs beside the wait below and is stopped
    # from here the moment the code arrives.
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        if not _CallbackHandler.received.wait(timeout):
            raise SystemExit(f"No redirect to {uri} within {timeout:.0f}s - giving up.")
    finally:
        server.shutdown()
        server.server_close()

    return _CallbackHandler.params
