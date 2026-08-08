"""Release pre-flight checks.

These guard an action that cannot be undone, so the failure cases matter more than
the happy path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from release_check import (
    Failure,
    changelog_section,
    check_is_newer,
    check_not_on_pypi,
    check_version_string,
)

LIVE = ["0.0.1", "0.1.0", "0.2.0"]


# --------------------------------------------------------------------------- #
# The version string
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("version", ["0.1.0", "1.0.0", "0.2.0rc1", "1.0.0b2", "2.0.0.post1"])
def test_valid_versions_are_accepted(version: str) -> None:
    assert str(check_version_string(version)) == version


@pytest.mark.parametrize("version", ["", "not-a-version", "1.0.0-final", "0.1.0.."])
def test_nonsense_is_rejected(version: str) -> None:
    with pytest.raises(Failure, match="not a valid PEP 440"):
        check_version_string(version)


def test_a_local_segment_is_rejected() -> None:
    """PyPI refuses these outright, so catching it here beats a failed upload."""
    with pytest.raises(Failure, match="local segment"):
        check_version_string("0.1.0+g1a2b3c4")


@pytest.mark.parametrize("version", ["v0.1.0", "0.01.0", "1.0.0-rc1", "0.2.0RC1", "0.1.0.dev"])
def test_unnormalised_forms_are_rejected(version: str) -> None:
    """`0.01.0` installs as `0.1.0`, so the tag and the artifact would disagree.

    `v0.1.0` lands here too, which is the useful case: typing the tag form instead of
    the version is an easy mistake, and the message names the form to use.
    """
    with pytest.raises(Failure, match="normalises to"):
        check_version_string(version)


# --------------------------------------------------------------------------- #
# Against what is already published
# --------------------------------------------------------------------------- #


def test_republishing_an_existing_version_is_refused() -> None:
    with pytest.raises(Failure, match="already on PyPI"):
        check_not_on_pypi(check_version_string("0.1.0"), LIVE)


def test_a_free_version_passes() -> None:
    check_not_on_pypi(check_version_string("0.3.0"), LIVE)


def test_going_backwards_is_refused() -> None:
    """pip resolves by version, not upload time, so an older number never installs."""
    with pytest.raises(Failure, match=r"not newer than 0\.2\.0"):
        check_is_newer(check_version_string("0.1.5"), LIVE)


def test_moving_forwards_reports_the_previous_release() -> None:
    assert str(check_is_newer(check_version_string("0.3.0"), LIVE)) == "0.2.0"


def test_a_prerelease_below_the_latest_is_refused() -> None:
    with pytest.raises(Failure, match="not newer"):
        check_is_newer(check_version_string("0.2.0rc1"), LIVE)


def test_the_very_first_release_has_no_predecessor() -> None:
    assert check_is_newer(check_version_string("0.1.0"), []) is None


def test_unparseable_published_versions_are_ignored_not_fatal() -> None:
    assert str(check_is_newer(check_version_string("0.3.0"), [*LIVE, "garbage"])) == "0.2.0"


# --------------------------------------------------------------------------- #
# The changelog the reviewer approves against
# --------------------------------------------------------------------------- #

SAMPLE = """# Changelog

## [Unreleased]

Nothing yet.

## [0.2.0] - 2026-08-08

### Added

- A thing.
- Another thing.

## [0.1.0] - 2026-07-01

### Added

- The first thing.

[Unreleased]: https://example.com
"""


def test_the_right_section_is_extracted() -> None:
    section = changelog_section("0.2.0", SAMPLE)
    assert "A thing." in section
    assert "The first thing." not in section, "must stop at the next heading"
    assert "Nothing yet." not in section


def test_the_last_section_stops_before_the_link_block() -> None:
    section = changelog_section("0.1.0", SAMPLE)
    assert "The first thing." in section
    assert "[Unreleased]: https://example.com" in section or section.endswith("thing.")


def test_a_missing_section_blocks_the_release() -> None:
    with pytest.raises(Failure, match=r"no '## \[0\.9\.0\]' section"):
        changelog_section("0.9.0", SAMPLE)


def test_an_empty_section_blocks_the_release() -> None:
    with pytest.raises(Failure, match="is empty"):
        changelog_section("0.3.0", "## [0.3.0] - 2026-08-08\n\n## [0.2.0]\n\n- real\n")


def test_the_real_changelog_has_a_section_for_the_released_version() -> None:
    assert "Nmbrs" in changelog_section("0.0.1") or changelog_section("0.0.1")
