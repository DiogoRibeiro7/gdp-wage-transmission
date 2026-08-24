# Contributing

Thanks for your interest in this project. It is an empirical research repository, so the
contribution rules are shaped by one requirement above all others: **a published number must be
reproducible from a frozen input by anyone who checks out the repository.**

## Getting set up

The project targets Python 3.11–3.13 and uses [Poetry](https://python-poetry.org/) 2.x.

```bash
poetry install          # installs runtime + dev dependencies from poetry.lock
poetry run pre-commit install
```

`poetry.lock` is committed on purpose. Install from it rather than resolving fresh, and if you
change a dependency, commit the regenerated lock file in the same change.

## Quality gates

Every change must pass the same three gates CI runs:

```bash
make check              # ruff check, mypy, pytest
```

or individually:

```bash
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src
poetry run pytest
```

`ruff format` is authoritative for formatting; do not hand-format around it. `mypy` runs in strict
mode over `src/`, so new public functions need annotations. Test coverage has a floor of 65% and
should move up, not down.

## Reproducibility rules

These are the rules that make the empirical claims defensible. Please treat them as hard
constraints rather than conventions.

1. **Never commit data.** `data/raw/`, `data/interim/`, `data/processed/` and `results/` are
   ignored. The only tracked data are the small synthetic sample, the frozen reference extract
   under `data/reference/`, and the query manifests that describe how to re-fetch everything else.
2. **Raw snapshots are immutable.** The download layer writes source bytes unchanged, with the
   query URL, retrieval timestamp and SHA-256 digest recorded alongside. If an official series is
   revised upstream, add a new vintage; never rewrite an existing one.
3. **Do not retro-fit a specification to a result.** The publication hierarchy in
   `config/publication.yml` records what was chosen before results were seen. Changing it is
   sometimes legitimate, but it must be argued for explicitly in the pull request, and a change
   made after inspecting results is specification drift, not a fix. Manuscripts and the
   specification locks that bind them to a source freeze are maintained outside this repository.
4. **Break dates are estimated, not assumed.** The structural-break and state-space models must
   not hard-code historical dates. Historical events belong in the interpretation of estimated
   regimes, not in their identification.
5. **Say when numbers move.** If a change alters any estimated output, the pull request must say
   which series changed and why. "Refactor" changes are expected to be numerically inert.

## Adding an estimator

New models live in `src/wage_transmission/models/` and should:

- take a tidy, validated panel and return a frozen dataclass of results, not a printed report;
- reuse `validation.py` for column checks and log-growth construction;
- serialise through `reporting.py` so output stays deterministic and diffable;
- come with a test that pins behaviour on the synthetic sample in `data/sample/`.

## Adding a data source

Source queries are declared in `config/data_sources.yml` and built in
`src/wage_transmission/data/`. A new source needs a canonicaliser that maps the official extract
onto the project's narrow panel schema, provenance metadata written through
`data/common.py`, and a test exercising the decoder against a small recorded response — not
against the live API.

Tests must not hit the network. Mark anything that genuinely needs outbound access with
`@pytest.mark.network` so it can be deselected.

## Pull requests

- Branch from `main`; keep one logical change per pull request.
- Fill in the pull request template, especially the section on empirical effect.
- Update `CHANGELOG.md` for anything user-facing. The changelog is organised by dated research
  revision rather than by semantic version alone, and records validation status for each.
- Commit messages: a short imperative subject line, and a body explaining *why* when the reason is
  not obvious from the diff.

## Reporting problems

Use the issue templates. Reproducibility problems — digest mismatches, revised official series,
results that will not reproduce — have their own template and are treated as high priority.
Security-relevant reports should follow [SECURITY.md](SECURITY.md) instead.
