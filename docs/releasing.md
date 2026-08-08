# Releasing

One workflow does everything: staging, verification, approval and live publish. There
are no local commands and no tags to push by hand.

See [../DESIGN.md](../DESIGN.md) for the SDK architecture.

## How to release

1. Edit `CHANGELOG.md`: move `Unreleased` into a `## [X.Y.Z] - YYYY-MM-DD` section and
   commit it (the GitHub web editor is fine).
2. **Actions → Release → Run workflow**, type the version, run it.
3. Watch it validate, build, publish to TestPyPI and verify the staged artifact.
4. Read the run summary — it shows the version, the previous release and the changelog.
5. Approve the **pypi** environment.

```
validate ──▶ build ──▶ TestPyPI ──▶ verify staged artifact
                                          │
                                 [ you approve here ]
                                          │
                                       PyPI ──▶ tag + GitHub Release
```

Everything before the approval is reversible. Everything after it is not.

### What gets checked before you are asked

The `validate` job refuses anything that cannot succeed, or that would succeed in a way
you cannot undo:

| Check | Why |
| --- | --- |
| Valid PEP 440, no local segment | PyPI rejects these outright |
| Normalised form | `0.01.0` installs as `0.1.0`; typing `v0.1.0` is caught too |
| Not already on PyPI | version numbers are permanent, even after deleting a release |
| Newer than PyPI's latest | pip resolves by version, not upload time, so an older number never installs |
| Tag `vX.Y.Z` does not exist | re-releasing would move a tag people may already have |
| `CHANGELOG.md` has that section | it is what you approve against |

Then `verify` installs the package from TestPyPI into a clean virtualenv and runs
`scripts/verify_install.py` against it, so the approval decision is made about an
artifact that has been installed and exercised, not just built.

It also compares the staged wheel's hash against the one just built. TestPyPI *skips*
duplicate filenames rather than replacing them, so without that check a re-run after a
code change would verify the old artifact and then promote the new one unverified.

### Where the version comes from

From the workflow input, not from a tag. `hatch-vcs` normally derives it from git
history; the build job sets `SETUPTOOLS_SCM_PRETEND_VERSION` instead, and the build then
asserts the wheel really carries the requested version.

The tag is created **after** PyPI accepts the upload, so a run that fails or is rejected
leaves nothing behind to clean up, and every tag records something that actually shipped.

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

**Narrow the tokens now that the project exists.** A project-scoped token can only be
created for a project already on the index, so the first upload had to use an
account-scoped token. `nmbrs-rest-api` is published on both indexes now, so create
tokens scoped to just this project, replace both secrets, and delete the
account-scoped ones. An account-scoped token can publish *anything* you own.

### 5. Verify

Start a release and stop at the approval gate. If it reaches TestPyPI and the
`verify` job passes, the wiring is correct. Rejecting leaves PyPI untouched.

---

## Testing a build without releasing

The release workflow stages to TestPyPI on every run, so the normal way to test a build
is to start a release and simply not approve it. TestPyPI keeps the artifact; PyPI is
untouched.

To pull whatever is currently staged and exercise it locally:

```bash
python scripts/try_testpypi.py                 # newest staged version
python scripts/try_testpypi.py --version 0.1.0 # a specific one
python scripts/try_testpypi.py --keep          # keep the venv to poke at it
```

It builds a throwaway virtualenv, installs from TestPyPI, runs
`scripts/verify_install.py` against it and deletes the venv. Exit code 0 means the
staged artifact is good. This is the same script the `verify` job runs.

`scripts/verify_install.py` also runs standalone against any installed copy. It imports
nothing from the source tree and needs no network — the HTTP layer is exercised through
`httpx.MockTransport` — so it tests the built artifact rather than the working directory,
and it refuses to run against a source checkout.

### Installing from TestPyPI by hand

Two things make the command longer than expected:

**TestPyPI does not mirror PyPI**, so `httpx` and `pydantic` are not there.
`--index-url` alone fails on the dependencies; you need both indexes.

**Pin the exact version** rather than reaching for `--pre`. PEP 440 allows a pre-release
when the specifier names one, whereas `--pre` also admits pre-release *dependencies*,
quietly changing what you are testing against.

```bash
pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  "nmbrs-rest-api==0.1.0"
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

- New fields appearing in Nmbrs responses are **not** a breaking change here. Reads
  return dicts straight from the API, so unknown fields simply arrive. When typed
  models land they will use `extra="allow"` for the same reason.
- Regenerating from an updated Nmbrs spec **can** be breaking: an endpoint that
  disappears upstream removes a method here. `tools/generate_resources.py` fails
  rather than silently dropping it. Treat that as a minor bump and call it out.
- An upstream change that silently alters the *meaning* of a field is undetectable from
  the spec. Nothing here can catch that; it gets fixed reactively.

Tags are always `v` + the version: `v0.1.0`, `v1.0.0rc1`.

---

## Recovery

### Validation blocked the run

Nothing was published — the `validate` job runs before anything else. The error names
the reason: version already on PyPI, not newer than the latest, missing changelog
section, tag already exists, or a form PyPI would reject. Fix and re-run.

### "TestPyPI already holds a different X"

An earlier run staged that version, and the code has changed since. TestPyPI skips
duplicate filenames rather than replacing them, so verification would have tested the
old artifact. Bump the version — staging versions are cheap.

### Rejected at the approval gate

Nothing reached PyPI and no tag was created. TestPyPI keeps what was staged. Fix the
problem and start a new run with a **higher** version, since the staged one is now
burned.

### Upload failed partway

Re-run the failed job from the GitHub UI; it re-downloads the same artifact rather than
rebuilding, so the version is unchanged. On staging `skip-existing: true` tolerates a
partial state. On PyPI a partial upload means you must bump.

### A bad release is live

Yank it. Yanking leaves the file installable for anyone who pinned it exactly, but hides
it from new resolution: **PyPI → Manage → Releases → Yank**.

Then release a fixed version. Do not delete — deletion burns the version number forever
and breaks anyone who pinned it. PyPI never allows reuse, even after deletion.

### A tag needs removing

Only possible if the run failed before the `tag` job, in which case there is no tag. If
one exists, something shipped under it; leave it alone and move forward.

---

## Pre-release checklist

- [ ] `main` is green in CI
- [ ] `CHANGELOG.md` has a section for this version, and `Unreleased` is emptied into it
- [ ] The version bump matches the nature of the changes
- [ ] Nothing secret in the diff — no tokens, no subscription keys, no token store files

Then: **Actions → Release → Run workflow**, type the version, and approve when the
summary looks right.
