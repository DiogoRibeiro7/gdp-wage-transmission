## Summary

<!-- What changes, and why. Link the issue this closes, if any. -->

## Type of change

- [ ] Bug fix
- [ ] New estimator, diagnostic or data source
- [ ] Refactor or tooling change with no effect on results
- [ ] Documentation

## Effect on empirical output

<!-- Required. State explicitly whether estimated numbers move. -->

- [ ] No estimated result changes.
- [ ] Estimated results change, and the reason is explained below.

<!-- If results change, describe which series, which specification, and by how much. -->

## Specification

- [ ] The publication hierarchy in `config/publication.yml` is unchanged.
- [ ] It is changed, and the PR explains why that is legitimate rather than
      specification drift.
- [ ] If a specification lock applies to this work, it still verifies. Lock
      artefacts are untracked, so this check is manual.

## Checklist

- [ ] `make check` passes locally (ruff, mypy, pytest).
- [ ] New behaviour is covered by tests.
- [ ] Documentation and `CHANGELOG.md` are updated where user-facing behaviour changed.
- [ ] No data, credentials or large binaries are committed.
