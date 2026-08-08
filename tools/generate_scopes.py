"""Generate src/nmbrs_rest/_scopes.py from the vendored OpenAPI spec.

Every operation in the Nmbrs spec declares the scopes that satisfy it. Baking that
table into the package is what lets a 403 say *which* scope is missing for *which*
operation instead of just "Forbidden".

Usage:
    python tools/generate_scopes.py
    python tools/generate_scopes.py --check   # exit 1 if the file is stale (for CI)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "src" / "nmbrs_rest" / "_spec" / "nmbrs-openapi.yaml"
DEST = ROOT / "src" / "nmbrs_rest" / "_scopes.py"

HEADER = '''"""Operation -> required scopes, generated from the vendored OpenAPI spec.

DO NOT EDIT. Regenerate with:

    python tools/generate_scopes.py

Any ONE of the scopes listed for an operation satisfies it: Nmbrs pairs a write
scope with its `.read` counterpart, and the write scope implies the read one.
"""

from __future__ import annotations

from typing import Final

'''


def load_operations(spec: dict[str, Any]) -> list[tuple[str, str, frozenset[str]]]:
    rows: list[tuple[str, str, frozenset[str]]] = []
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method in {"parameters", "servers", "summary", "description"}:
                continue
            security = operation.get("security") or []
            scopes: set[str] = set()
            for requirement in security:
                for names in requirement.values():
                    scopes.update(names)
            rows.append((method.upper(), path, frozenset(scopes)))
    rows.sort(key=lambda r: (r[1], r[0]))
    return rows


def render(rows: list[tuple[str, str, frozenset[str]]]) -> str:
    lines = [HEADER]
    lines.append("REQUIRED_SCOPES: Final[dict[tuple[str, str], frozenset[str]]] = {")
    for method, path, scopes in rows:
        if scopes:
            joined = ", ".join(f'"{s}"' for s in sorted(scopes))
            value = f"frozenset({{{joined}}})"
        else:
            value = "frozenset()"
        lines.append(f'    ("{method}", "{path}"): {value},')
    lines.append("}")
    lines.append("")

    all_scopes = sorted({s for _, _, scopes in rows for s in scopes})
    lines.append("#: Every scope referenced by at least one operation.")
    lines.append("KNOWN_SCOPES: Final[frozenset[str]] = frozenset(")
    lines.append("    {")
    for scope in all_scopes:
        lines.append(f'        "{scope}",')
    lines.append("    }")
    lines.append(")")
    lines.append("")
    lines.append("#: Required for a refresh token. Guards no operation.")
    lines.append('OFFLINE_ACCESS: Final[str] = "offline_access"')
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    args = parser.parse_args()

    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    rows = load_operations(spec)
    generated = render(rows)

    current = DEST.read_text(encoding="utf-8") if DEST.exists() else ""
    if current == generated:
        print(f"up to date ({len(rows)} operations)")
        return 0

    if args.check:
        print("STALE: _scopes.py does not match the vendored spec.")
        print("Run: python tools/generate_scopes.py")
        return 1

    DEST.write_text(generated, encoding="utf-8")
    print(f"wrote {DEST} ({len(rows)} operations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
