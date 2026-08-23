## Summary

<!-- What changes, and why. Link the issue this closes, if any. -->

## Type of change

- [ ] Bug fix
- [ ] New estimator, diagnostic or data source
- [ ] Refactor or tooling change with no effect on results
- [ ] Documentation
- [ ] Manuscript or publication artefact

## Effect on empirical output

<!-- Required. State explicitly whether estimated numbers move. -->

- [ ] No estimated result changes.
- [ ] Estimated results change, and the reason is explained below.

<!-- If results change, describe which series, which specification, and by how much. -->

## Specification locks

- [ ] No locked specification (`paper/specification_lock.json`,
      `papers/*/analysis_lock.json`) is modified.
- [ ] A lock is modified, and the PR explains why the change is legitimate
      rather than specification drift.

## Checklist

- [ ] `make check` passes locally (ruff, mypy, pytest).
- [ ] New behaviour is covered by tests.
- [ ] Documentation and `CHANGELOG.md` are updated where user-facing behaviour changed.
- [ ] No data, credentials or large binaries are committed.
