# Releasing

How `nmbrs-rest-api` gets published to TestPyPI (staging) and PyPI (live).

See [../DESIGN.md](../DESIGN.md) for the SDK architecture.

| | Trigger | Index | Approval |
|---|---|---|---|
| **Staging** | `workflow_dispatch` on any commit | [TestPyPI](https://test.pypi.org/project/nmbrs-rest-api/) | none |
| **Live** | push a `v*` tag | [PyPI](https://pypi.org/project/nmbrs-rest-api/) | required reviewer |

The version is derived from git, never hand-edited. `pyproject.toml` has no version field.

---

## One-time setup

Do this once, before the first release. Steps 3 and 4 have an ordering catch — read them together.

### 1. Create the two GitHub Environments

`Settings` → `Environments` → `New environment`. Create both:

- `testpypi`
- `pypi`

The names must match exactly; the workflow references them by name.

### 2. Protect the live environment

On the `pypi` environment only:

- Tick **Required reviewers** and add yourself.
- Optionally restrict **Deployment branches and tags** to the tag pattern `v*`.

This is what makes a tag push pause and wait for you before anything reaches PyPI
permanently. Without it a mistyped tag publishes immediately, and **PyPI never lets
you reuse a version number** — not even after deleting the release.

### 3. Add the TestPyPI token

On the `testpypi` environment → `Add environment secret`:

| Name | Value |
|---|---|
| `TEST_PYPI_API_TOKEN` | your TestPyPI token, including the `pypi-` prefix |

### 4. Add the PyPI token

On the `pypi` environment → `Add environment secret`:

| Name | Value |
|---|---|
| `PYPI_API_TOKEN` | your PyPI token, including the `pypi-` prefix |

**The ordering catch:** a project-scoped token can only be created for a project that
already exists on the index. Since `nmbrs-rest-api` has never been uploaded, your first
upload must use an **account-scoped** token. After the first successful publish, go back
to PyPI, create a new token scoped to just the `nmbrs-rest-api` project, replace the
secret, and delete the account-scoped one. Same applies to TestPyPI.

### 5. Verify

Run a staging publish (below). If it lands on TestPyPI, the wiring is correct.

---

## Publishing to staging (TestPyPI)

Any commit, any time, no tag needed.

```powershell
gh workflow run release.yml
```

Or: `Actions` → `Release` → `Run workflow` → `Run workflow`.

### What version do I get?

From an untagged commit, the version is derived from the last tag plus the commit
distance — for example `0.1.1.dev7`, or `0.0.1.dev1` when no tag exists at all.

There is deliberately **no local version segment** (`+g1a2b3c4`). PyPI and TestPyPI reject
any upload whose version contains one, and staging publishes untagged commits by
definition, so this is enforced by `local_scheme = "no-local-version"` in `pyproject.toml`
and asserted by both CI and the release workflow.

Re-dispatching on the *same* commit produces the *same* version. TestPyPI refuses
duplicate files, so the staging job sets `skip-existing: true` and the re-run is a no-op
rather than a failure. To get a fresh version, make a commit.

### Verifying a staging release

```bash
python scripts/try_testpypi.py
```

That is the whole procedure. It builds a throwaway virtualenv, resolves the newest
staged version, installs it from TestPyPI, runs the checks in
`scripts/verify_install.py` against it, and deletes the venv. Exit code 0 means the
staged artifact is good.

Useful flags:

| Flag | Why |
| --- | --- |
| `--wait 300` | Poll until a version appears that was not there when the script started. Use it right after dispatching the workflow — index propagation lags the upload by a few seconds. |
| `--keep` | Keep the venv at `build/testpypi-venv` and print how to activate it, for poking around by hand. |
| `--version X` | Install an exact version instead of the newest. |

`scripts/verify_install.py` can also be run on its own against any already-installed
copy of the package. It imports nothing from the source tree and needs no network —
the HTTP layer is exercised through `httpx.MockTransport` — so it is a genuine test of
the built artifact rather than of the working directory. It refuses to run against a
source checkout, since that would verify nothing about what was published.

#### Doing it by hand

Two things make the manual command longer than people expect:

**TestPyPI does not mirror PyPI**, so it has no copy of `httpx` or `pydantic`.
`--index-url` alone fails on the dependencies; you need both indexes.

**Untagged builds are dev versions** (`0.0.1.dev7`), which pip skips by default.
Pin the exact version rather than reaching for `--pre` — PEP 440 allows a pre-release
when the specifier names one, whereas `--pre` also lets pre-release *dependencies* in,
quietly changing what you are testing against.

```powershell
python -m venv .venv-check
.\.venv-check\Scripts\Activate.ps1
pip install `
  --index-url https://test.pypi.org/simple/ `
  --extra-index-url https://pypi.org/simple/ `
  "nmbrs-rest-api==0.0.1.dev7"
python -c "import nmbrs_rest; print(nmbrs_rest.__version__)"
```

POSIX equivalent — same flags, `\` for line continuation:

```bash
python -m venv .venv-check
source .venv-check/bin/activate
pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  "nmbrs-rest-api==0.0.1.dev7"
```

---

## Publishing to live (PyPI)

```powershell
# 1. Make sure main is green and CHANGELOG.md is updated.
git switch main
git pull

# 2. Tag. The tag IS the version: v0.1.0 publishes 0.1.0.
git tag v0.1.0
git push origin v0.1.0
```

That triggers `release.yml`:

1. **build** — builds sdist + wheel, runs `twine check --strict`, asserts the version has
   no local segment, and **verifies the tag matches the built version**. A tag of `v0.2.0`
   that produces `0.1.1.dev0` fails here rather than publishing something mislabelled.
2. **publish-pypi** — pauses. You get a GitHub notification; approve it under the run's
   `Review deployments` button.
3. **github-release** — creates the GitHub Release with generated notes and attaches the
   built artifacts.

The distribution is built **once** and both publish jobs consume that same artifact, so
what gets validated is exactly what gets uploaded.

### After publishing

```powershell
pip install nmbrs-rest-api==0.1.0
python -c "import nmbrs_rest; print(nmbrs_rest.__version__)"
```

---

## Version numbering

Semantic versioning, with pre-1.0 rules while the SDK is unstable:

| Change | Bump |
|---|---|
| Breaking change to the SDK's own API | minor while `0.x`, major after `1.0` |
| New endpoint coverage, new resource, new optional argument | minor |
| Bug fix, docs, internal refactor | patch |

**What counts as breaking is complicated by upstream.** The Nmbrs REST API is
*unversioned* — Nmbrs ships additive changes with no notice and no version bump. So:

- New fields appearing in Nmbrs responses are **not** a breaking change here. Models use
  `extra="allow"` precisely so this cannot break users.
- Regenerating models from an updated Nmbrs spec **can** be breaking if a field was removed
  or retyped upstream. Treat that as a minor bump and call it out in `CHANGELOG.md`.
- An upstream change that silently alters the *meaning* of a field is undetectable from
  the spec. Nothing here can catch that; it gets fixed reactively.

Tags are always `v` + the version: `v0.1.0`, `v1.0.0rc1`.

---

## Recovery

### The version already exists on the index

PyPI does not allow re-uploading a version, even one you deleted. Bump and re-release —
`v0.1.1`. Never try to reuse the number.

On TestPyPI the staging job uses `skip-existing`, so this is a no-op, not an error.

### Wrong tag pushed

If the release has **not** been approved yet, cancel the workflow run first, then:

```powershell
git tag -d v0.1.0
git push origin :refs/tags/v0.1.0
```

Then tag correctly. If it *was* already published to PyPI, you cannot undo it — see
yanking below.

### Tag and version disagree

The build job fails with `Tag vX implies version Y but the build produced Z`. Usual causes:

- The tag is not on the commit you think it is.
- `fetch-depth: 0` missing, so the tag was not fetched. Already set in both workflows —
  if you copy these jobs elsewhere, carry it over.
- Locally only: a **dirty working tree** makes `hatch-vcs` bump to the next dev version.
  Tagging `v0.1.0` with uncommitted changes builds `0.1.1.dev0`, not `0.1.0`. CI always
  checks out clean, so this is a local-build surprise, not a pipeline one.

### Build passed but upload failed partway

Fix the cause and re-run the failed job from the GitHub UI — it re-downloads the same
artifact rather than rebuilding, so the version is unchanged. If some files uploaded and
others did not, `skip-existing: true` on staging tolerates the partial state. On PyPI a
partial upload means you must bump.

### A bad release is live

Yank it. Yanking leaves the file installable for anyone who pinned it exactly, but hides it
from new resolution:

```powershell
# PyPI web UI: project > Manage > Releases > Yank
```

Then release a fixed version. Do not delete — deletion burns the version number forever
and breaks anyone who pinned it.

---

## Pre-release checklist

- [ ] `main` is green in CI
- [ ] `CHANGELOG.md` has an entry for this version, and `Unreleased` is emptied into it
- [ ] Staging publish done and installed from TestPyPI into a clean venv
- [ ] Version bump matches the nature of the changes
- [ ] Nothing secret in the diff — no tokens, no subscription keys, no token store files

```powershell
git switch main; git pull
gh workflow run release.yml          # staging
# ...verify from TestPyPI...
git tag v0.1.0; git push origin v0.1.0
# ...approve the deployment in the GitHub UI...
```
