#!/usr/bin/env python3
"""Pre-flight checks for a release, and the reviewer's summary.

    python tools/release_check.py preflight --version 0.1.0
    python tools/release_check.py staging-matches --version 0.1.0 --wheel dist/x.whl

``preflight`` refuses anything that cannot succeed, or that would succeed in a way
you cannot undo:

* a version PyPI will reject (bad PEP 440, local segment)
* a version already on PyPI - version numbers are permanent, even after deletion
* a version that is not newer than what is already published
* a tag that already exists

A missing CHANGELOG section is *not* a blocker - the summary falls back to the
commits since the last tag, so there is still something to approve against.

``staging-matches`` closes the one hole in publish-to-staging-then-promote: TestPyPI
skips a duplicate filename rather than failing, so a re-run after a code change would
verify the *old* artifact and promote the new one unverified. Comparing hashes turns
that into a loud failure.

Both write GitHub step summaries when ``GITHUB_STEP_SUMMARY`` is set, so the approval
page shows the version and the changelog rather than just a job name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"

DIST_NAME = "nmbrs-rest-api"
PYPI = "https://pypi.org/simple/"
TESTPYPI = "https://test.pypi.org/simple/"
SIMPLE_JSON = "application/vnd.pypi.simple.v1+json"


class Failure(Exception):
    """A reason the release must not proceed."""


# --------------------------------------------------------------------------- #
# Index queries
# --------------------------------------------------------------------------- #


def index_data(base: str) -> dict[str, object]:
    request = urllib.request.Request(f"{base}{DIST_NAME}/", headers={"Accept": SIMPLE_JSON})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload: dict[str, object] = json.load(response)
            return payload
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"versions": [], "files": []}
        raise


def published(base: str) -> list[str]:
    raw = index_data(base).get("versions", [])
    return [str(v) for v in raw] if isinstance(raw, list) else []


def parse_all(versions: list[str]) -> list[Version]:
    out = []
    for raw in versions:
        try:
            out.append(Version(raw))
        except InvalidVersion:
            continue
    return out


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #


def check_version_string(version: str) -> Version:
    try:
        parsed = Version(version)
    except InvalidVersion as exc:
        raise Failure(
            f"{version!r} is not a valid PEP 440 version. Use e.g. 0.1.0, 1.2.3rc1."
        ) from exc
    if parsed.local is not None:
        raise Failure(
            f"{version!r} carries the local segment {parsed.local!r}. PyPI rejects local versions."
        )
    if str(parsed) != version:
        raise Failure(
            f"{version!r} normalises to {parsed!s}. Use the normalised form so the tag, "
            "the artifact and the index all agree."
        )
    return parsed


def check_not_on_pypi(parsed: Version, live: list[str]) -> None:
    if str(parsed) in live:
        raise Failure(
            f"{parsed} is already on PyPI. Version numbers are permanent there - "
            "even deleting a release does not free the number. Pick a higher one."
        )


def check_is_newer(parsed: Version, live: list[str]) -> Version | None:
    existing = parse_all(live)
    if not existing:
        return None
    highest = max(existing)
    if parsed <= highest:
        raise Failure(
            f"{parsed} is not newer than {highest}, which is already on PyPI. "
            "pip resolves by version, not by upload time, so this would never install."
        )
    return highest


def changelog_section(version: str, text: str | None = None) -> str:
    body = text if text is not None else CHANGELOG.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^##\s*\[{re.escape(version)}\][^\n]*\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        raise Failure(
            f"CHANGELOG.md has no '## [{version}]' section. That section is what the "
            "reviewer approves against, so it has to exist before the release runs."
        )
    section = match.group(1).strip()
    if not section:
        raise Failure(f"The '## [{version}]' section in CHANGELOG.md is empty.")
    return section


def recent_commits(version: str) -> str:
    """Commits since the last tag, as a stand-in when the changelog is not written."""
    try:
        previous = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        span = f"{previous}..HEAD" if previous else "HEAD"
        log = subprocess.run(
            ["git", "log", span, "--no-merges", "--format=- %s"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError:
        return "_No changelog section, and git log is unavailable._"

    since = f"since {previous}" if previous else "so far"
    header = f"_No `## [{version}]` section in CHANGELOG.md, so here are the commits {since}:_"
    if not log:
        return f"{header}\n\n_(none)_"
    return f"{header}\n\n{log}"


def write_summary(markdown: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    print(markdown)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def preflight(version: str) -> int:
    try:
        parsed = check_version_string(version)
        live = published(PYPI)
        staged = published(TESTPYPI)
        check_not_on_pypi(parsed, live)
        previous = check_is_newer(parsed, live)
    except Failure as exc:
        write_summary(f"## Release blocked\n\n**{exc}**\n")
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    # A missing or empty changelog section is a nudge, not a gate. The reviewer still
    # gets the commit list, which is enough to approve against.
    try:
        section = changelog_section(version)
    except Failure:
        section = recent_commits(version)
        print(f"::warning::CHANGELOG.md has no '## [{version}]' section; using commits instead")

    already_staged = str(parsed) in staged
    staged_note = "yes - artifacts will be compared" if already_staged else "no"
    lines = [
        f"# Release {parsed}",
        "",
        "| | |",
        "| --- | --- |",
        f"| Version | `{parsed}` |",
        f"| Previous on PyPI | `{previous}` |" if previous else "| Previous on PyPI | none |",
        f"| Tag to be created | `v{parsed}` |",
        f"| Already on TestPyPI | {staged_note} |",
        "",
        "## Changelog",
        "",
        section,
        "",
        "---",
        "",
        "Approving the **pypi** environment publishes this to PyPI permanently and "
        "creates the tag. Rejecting it leaves PyPI untouched; TestPyPI keeps whatever "
        "was staged.",
    ]
    write_summary("\n".join(lines))
    return 0


def staging_matches(version: str, wheel: Path) -> int:
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    raw = index_data(TESTPYPI).get("files", [])
    files: list[object] = raw if isinstance(raw, list) else []
    remote = [
        f
        for f in files
        if isinstance(f, dict)
        and str(f.get("filename", "")).endswith(".whl")
        and f"-{version}-" in str(f.get("filename", ""))
    ]
    if not remote:
        print(f"no wheel for {version} on TestPyPI yet; nothing to compare")
        return 0

    hashes = remote[0].get("hashes", {})
    published_digest = str(hashes.get("sha256", "")) if isinstance(hashes, dict) else ""
    if published_digest and published_digest != digest:
        message = (
            f"TestPyPI already holds a *different* {version}. It was uploaded by an "
            "earlier run, and TestPyPI skips duplicate filenames rather than replacing "
            "them - so staging just verified that older artifact, not this build. "
            "Bump the version."
        )
        write_summary(f"## Release blocked\n\n**{message}**\n")
        print(f"::error::{message}", file=sys.stderr)
        return 1

    print(f"TestPyPI artifact matches this build (sha256 {digest[:16]}...)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    pre = sub.add_parser("preflight", help="validate the version and changelog")
    pre.add_argument("--version", required=True)

    match = sub.add_parser("staging-matches", help="staged artifact is this build")
    match.add_argument("--version", required=True)
    match.add_argument("--wheel", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "preflight":
        return preflight(args.version)
    return staging_matches(args.version, args.wheel)


if __name__ == "__main__":
    raise SystemExit(main())
