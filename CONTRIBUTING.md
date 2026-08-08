# Contributing

Thanks for helping out. This project is at the design stage, so the most useful
contributions right now are review of [DESIGN.md](DESIGN.md),
[docs/authentication.md](docs/authentication.md) and [docs/errors.md](docs/errors.md) —
particularly from anyone who has actually integrated with Nmbrs.

## Setup

```powershell
git clone https://github.com/LarsKluijtmans/nmbrs_rest_api
cd nmbrs_rest_api
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

POSIX: `python3 -m venv venv && source venv/bin/activate && pip install -e '.[dev]'`

Clone with full history. The version is derived from git tags, so a shallow clone produces
a wrong version or fails to build.

## Checks

Run all of these before opening a PR — CI runs the same ones:

```powershell
ruff check .
ruff format --check .
mypy
pytest
```

`ruff format .` fixes formatting. `ruff check --fix .` fixes what it safely can.

Type checking is `mypy --strict`. New code needs annotations.

## Generated models are not editable by hand

The `nmbrs_rest.models` package is **generated** from a vendored copy of the Nmbrs OpenAPI
spec. Hand-edits are overwritten on the next regeneration.

To change a model, change the input or the generator:

```powershell
python tools/fetch_spec.py        # refresh the vendored spec from Nmbrs
python tools/generate_models.py   # regenerate
```

Commit the regenerated output along with the spec change so the diff is reviewable.

Curated re-exports live in `models/__init__.py` and *are* hand-maintained — they exist so
an upstream rename doesn't break user imports.

## Upstream is unversioned

The Nmbrs REST API has no versioning and ships additive changes without notice. Two rules
follow:

- Models tolerate unknown fields (`extra="allow"`). Do not tighten this.
- Never assume a field's absence is permanent, or that the documented error code list is
  complete. Error handling must degrade gracefully on codes we have never seen.

## Testing

No Nmbrs sandbox exists. Tests are layered:

- **Unit** — `respx` mocks over httpx. No network. This is where nearly everything belongs.
- **Contract** — responses validated against the vendored spec, so a spec update that
  breaks our assumptions fails CI.
- **Live smoke** — opt-in via environment variables against your own Nmbrs demo
  environment, read-only, skipped by default. Never commit credentials.

## Pull requests

- Branch off `main`.
- Keep the change focused; unrelated refactors make review harder.
- Add tests for behaviour changes.
- Update [CHANGELOG.md](CHANGELOG.md) under `Unreleased`.
- Explain *why*, not just *what* — the reasoning is what reviewers cannot reconstruct.

Commit messages: imperative mood, one logical change per commit. Conventional Commits are
welcome but not enforced.

## Releases

Maintainers release by pushing a `v*` tag; contributors do not need to do anything. The
full process is in [docs/releasing.md](docs/releasing.md).

## Security

Do not open a public issue for a vulnerability. See [SECURITY.md](SECURITY.md).
