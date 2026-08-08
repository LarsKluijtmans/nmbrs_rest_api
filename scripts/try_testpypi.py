#!/usr/bin/env python3
"""Install the staged package from TestPyPI into a throwaway venv and test it.

    python scripts/try_testpypi.py                 # newest staged version
    python scripts/try_testpypi.py --wait 300      # poll until a new upload lands
    python scripts/try_testpypi.py --version 0.0.1.dev2
    python scripts/try_testpypi.py --keep          # keep the venv to poke at it

Stdlib only, so it runs before anything is installed.

Two details this script exists to get right, both of which bite people who type the
pip command by hand:

* TestPyPI does not mirror the real index, so ``httpx`` and ``pydantic`` are not
  there. Installing needs ``--index-url`` at TestPyPI *and* ``--extra-index-url``
  at PyPI, or dependency resolution fails.
* Untagged builds are dev versions (``0.0.1.dev2``), which pip skips by default.
  Rather than reach for ``--pre`` - which would also let pre-release *dependencies*
  in, quietly changing what you are testing against - this resolves the exact
  version and pins it. PEP 440 permits a pre-release when the specifier names one.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import venv
from pathlib import Path

DIST_NAME = "nmbrs-rest-api"
TESTPYPI_SIMPLE = "https://test.pypi.org/simple/"
PYPI_SIMPLE = "https://pypi.org/simple/"
SIMPLE_JSON = "application/vnd.pypi.simple.v1+json"

HERE = Path(__file__).resolve().parent
VERIFIER = HERE / "verify_install.py"


def log(message: str) -> None:
    print(f"==> {message}", flush=True)


def available_versions() -> list[str]:
    """Every version currently on TestPyPI, unordered (PEP 691 simple API)."""
    request = urllib.request.Request(
        f"{TESTPYPI_SIMPLE}{DIST_NAME}/", headers={"Accept": SIMPLE_JSON}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        raise
    versions = payload.get("versions", [])
    return [str(v) for v in versions]


def wait_for_upload(deadline: float, known: set[str], target: str | None = None) -> list[str]:
    """Poll until the version we care about shows up.

    With ``target`` that is a specific version - the release workflow knows exactly
    what it just uploaded, and waiting for "something new" would sit out the whole
    timeout because the upload already happened. Without one, any version we did not
    see at startup counts.
    """
    while True:
        versions = available_versions()
        if target is not None:
            if target in versions:
                log(f"{target} is on TestPyPI")
                return versions
        else:
            fresh = set(versions) - known
            if fresh:
                log(f"new on TestPyPI: {', '.join(sorted(fresh))}")
                return versions
        if time.monotonic() >= deadline:
            if target is not None:
                sys.exit(f"{target} did not appear on TestPyPI before the timeout")
            log("timed out waiting; using whatever is there now")
            return versions
        time.sleep(10)


def venv_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(python: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(python), *args], check=True, text=True)


def newest(python: Path, versions: list[str]) -> str:
    """Sort with PEP 440 semantics, using `packaging` inside the fresh venv."""
    script = (
        "import json,sys\n"
        "from packaging.version import Version\n"
        "print(max(json.loads(sys.argv[1]), key=Version))\n"
    )
    result = subprocess.run(
        [str(python), "-c", script, json.dumps(versions)],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", help="exact version to install (default: newest staged)")
    parser.add_argument(
        "--wait",
        type=int,
        metavar="SECONDS",
        default=0,
        help="poll TestPyPI until a version appears that is not there yet",
    )
    parser.add_argument("--keep", action="store_true", help="keep the venv instead of deleting it")
    parser.add_argument(
        "--python", default=sys.executable, help="interpreter to build the venv from"
    )
    args = parser.parse_args()

    if not VERIFIER.is_file():
        sys.exit(f"missing {VERIFIER}")

    log(f"querying TestPyPI for {DIST_NAME}")
    known = set(available_versions())
    if known:
        log(f"currently staged: {', '.join(sorted(known))}")
    else:
        log("nothing staged yet")

    versions = sorted(known)
    if args.wait:
        wanted = f"{args.version} to appear" if args.version else "a new upload"
        log(f"waiting up to {args.wait}s for {wanted}")
        versions = wait_for_upload(time.monotonic() + args.wait, known, args.version)

    if not versions and not args.version:
        sys.exit(
            f"no versions of {DIST_NAME} on TestPyPI yet.\n"
            "Run the Release workflow first:  gh workflow run release.yml"
        )

    root = Path((args.keep and "build/testpypi-venv") or tempfile.mkdtemp(prefix="nmbrs-testpypi-"))
    if args.keep and root.exists():
        shutil.rmtree(root)
    root.parent.mkdir(parents=True, exist_ok=True)

    try:
        log(f"creating venv at {root}")
        venv.EnvBuilder(with_pip=True, clear=True).create(root)
        python = venv_python(root)

        run(python, "-m", "pip", "install", "--quiet", "--upgrade", "pip", "packaging")

        target = args.version or newest(python, versions)
        log(f"installing {DIST_NAME}=={target} from TestPyPI")

        run(
            python,
            "-m",
            "pip",
            "install",
            f"{DIST_NAME}=={target}",
            "--index-url",
            TESTPYPI_SIMPLE,
            # Dependencies live on the real index, not TestPyPI.
            "--extra-index-url",
            PYPI_SIMPLE,
        )

        log("running verification checks against the installed package")
        print()
        # cwd is the venv root so the repo's source tree cannot shadow the install.
        result = subprocess.run(
            [str(python), str(VERIFIER)],
            cwd=root,
            check=False,
            text=True,
        )
        print()

        if result.returncode == 0:
            log(f"{DIST_NAME}=={target} from TestPyPI works")
        else:
            log(f"{DIST_NAME}=={target} from TestPyPI FAILED verification")

        if args.keep:
            activate = root / ("Scripts/activate" if sys.platform == "win32" else "bin/activate")
            log(f"venv kept: {root}")
            print(f"    source {activate}   # or {activate}.bat on cmd")
            print(f'    {python} -c "import nmbrs_rest; print(nmbrs_rest.__version__)"')

        return result.returncode
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
