"""Smoke tests.

These exist so the packaging and release pipeline can be exercised end to end
before the SDK implementation lands. Replace with real tests as modules appear.
"""

from __future__ import annotations

from packaging.version import Version

import nmbrs_rest


def test_version_is_populated() -> None:
    assert isinstance(nmbrs_rest.__version__, str)
    assert nmbrs_rest.__version__


def test_version_is_pep440_and_uploadable() -> None:
    """A local version segment makes the artifact unpublishable to PyPI/TestPyPI."""
    parsed = Version(nmbrs_rest.__version__)
    assert parsed.local is None, (
        f"version {nmbrs_rest.__version__!r} carries a local segment; "
        "PyPI and TestPyPI reject these. Check local_scheme in pyproject.toml."
    )
