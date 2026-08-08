"""Refresh the vendored Nmbrs OpenAPI spec.

The spec is not published as a plain file. It lives as a node inside the Nmbrs
Stoplight project and is retrievable unauthenticated through Stoplight's export
route:

    /api/v1/projects/{workspace}/{project}/nodes/{uri}

Usage:
    python tools/fetch_spec.py           # fetch and write if changed
    python tools/fetch_spec.py --check   # exit 1 if upstream differs (for CI)

The Nmbrs REST API is unversioned and ships additive changes without notice, so
re-running this periodically is how we notice them at all.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.parse
import urllib.request
from pathlib import Path

WORKSPACE = "nmbrs"
PROJECT = "nmbrs-restapi"
NODE_URI = "api-design/nmbrs-api-Global.v1.yaml"

SPEC_URL = (
    f"https://{WORKSPACE}.stoplight.io/api/v1/projects/{WORKSPACE}/{PROJECT}"
    f"/nodes/{urllib.parse.quote(NODE_URI, safe='')}"
)

DEST = (
    Path(__file__).resolve().parent.parent / "src" / "nmbrs_rest" / "_spec" / "nmbrs-openapi.yaml"
)


def fetch() -> bytes:
    request = urllib.request.Request(SPEC_URL, headers={"Accept": "text/yaml, */*"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return bytes(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if upstream differs")
    args = parser.parse_args()

    upstream = fetch()
    current = DEST.read_bytes() if DEST.exists() else b""

    upstream_hash = hashlib.sha256(upstream).hexdigest()
    current_hash = hashlib.sha256(current).hexdigest()

    if upstream_hash == current_hash:
        print(f"unchanged ({upstream_hash[:12]}, {len(upstream)} bytes)")
        return 0

    if args.check:
        print(f"DIFFERS: vendored {current_hash[:12]} != upstream {upstream_hash[:12]}")
        print("Run `python tools/fetch_spec.py` then regenerate.")
        return 1

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_bytes(upstream)
    print(f"updated {DEST}")
    print(f"  {current_hash[:12]} -> {upstream_hash[:12]} ({len(upstream)} bytes)")
    print("Now run: python tools/generate_scopes.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
