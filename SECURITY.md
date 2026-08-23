# Security policy

## Scope

This repository is a research codebase. It has no server component and stores no credentials, but
it does execute code that fetches data over the network from official statistical APIs and parses
the responses. The realistic security surface is therefore:

- the HTTP download layer in `src/wage_transmission/data/`;
- parsing of downloaded SDMX/CSV payloads;
- any dependency vulnerability that reaches those paths.

Data-quality problems — a wrong series, a digest mismatch, a revised upstream vintage — are **not**
security issues. Please report those with the "Data or result issue" issue template.

## Supported versions

The `main` branch is the only supported version. Fixes are applied there and released in the next
tagged version.

| Version | Supported |
| ------- | --------- |
| `main`  | yes       |
| 0.6.x   | yes       |
| < 0.6   | no        |

## Reporting a vulnerability

Please report privately rather than opening a public issue:

1. Open a draft advisory through **Security → Advisories → Report a vulnerability** on this
   repository, which keeps the report private until a fix is published; or
2. contact the maintainer, [@DiogoRibeiro7](https://github.com/DiogoRibeiro7), directly.

Please include the affected version or commit, the conditions needed to trigger the issue, and the
impact you believe it has. A proof of concept is welcome but not required.

You can expect an acknowledgement within seven days and an assessment within thirty. If a fix is
warranted, the advisory will credit you unless you ask otherwise.

## Dependencies

Dependency updates are proposed monthly by Dependabot and validated by the full CI suite before
merge. If you find a vulnerable transitive dependency, an issue or pull request bumping
`poetry.lock` is welcome.
