# Contributing

Thank you for looking. This is a small project with three modules in three languages, and most of
what follows exists so that a change to one of them does not break the other two in silence.

Start with [docs/architecture.md](docs/architecture.md) for how the pieces fit together and
[docs/development.md](docs/development.md) for how to run and test each one.

## Licensing

This project is **AGPL-3.0-or-later**. By contributing you agree that your contribution is licensed
under the same terms. There is no CLA.

If your change copies or adapts code from another project, say so in the pull request and add the
attribution to [NOTICE](NOTICE) in the same commit — including the upstream licence and a statement
of what you changed. Apache-2.0 requires the second part; getting it right is not optional. Note that
[NOTICE](NOTICE) covers *derived source only*, not the dependency list.

## Before you write code

Open an issue first for anything that changes behaviour, adds a dependency, or alters one of the two
cross-module contracts (the Kafka payload, the REST API). Typo fixes, documentation and tests do not
need one.

## The rules a change must not break

Each of these is enforced by a test. If you find yourself deleting one of those tests to make a
change pass, the change is the thing that is wrong.

- **The detector's architecture boundary.** Only `adapters.py`, `annotate.py` and
  `KafkaEventPublisher.connect` may import `cv2`, `ultralytics`, `kafka`, `torch` or `numpy`.
  `tests/test_architecture.py` checks this by reading the AST, so a lazy import inside a function in
  any other module is still a violation. This is what keeps the unit suite running in under two
  seconds on a machine with no CV stack.
- **`detector/config.example.yaml` must parse back equal to the built-in defaults.** A test asserts
  it. Add a setting, document it there in the same commit.
- **The wire format is asserted against the Java source.** `detector/tests/test_events.py` reads
  `RawEvent.java` rather than a copy of its field list, because `@JsonIgnoreProperties(ignoreUnknown
  = true)` means a misspelled key is accepted in silence and arrives as `null`.
- **Secrets have no committed default.** `ProductionConfigurationTest` reads
  `engine/src/main/resources/application.yml` as raw text and pins the exact set of environment
  variables that have no fallback. Adding a fallback for a secret makes it fail; so does making a
  non-secret required.
- **CORS may not be `*`.** `SecurityConfiguration` refuses a wildcard at startup.

## Tests

Write the test first for a behaviour change, and make it fail for the right reason before you make it
pass. Characterization tests — tests that pin existing behaviour before you change it — are welcome
on their own; several of this project's commits are exactly that.

Naming matters, because both build tools select by filename:

- **detector**: `tests/test_*.py`. Anything needing ultralytics, opencv or real weights goes under
  `tests/integration/` and is marked `requires_ultralytics`, so the fast tier stays fast.
- **engine**: Surefire runs `*Test` (no Docker, seconds). Failsafe runs `*IT` (Testcontainers,
  Docker required). A test named neither runs nowhere — that is exactly how two test classes in this
  repository were silently skipped for the whole graduation project.
- **web**: Vitest, `src/**/*.{test,spec}.{js,jsx}` (`vite.config.js`), run with `npm test`.

One trap worth repeating from the commit log: a targeted `-Dtest=` run can report green on tests
that never executed. Surefire 3.5.6 fixed the `@Nested` half of it — naming the class now runs the
nested tests too — but naming a *method* that lives in a nested class runs nothing at all and still
exits successfully. Verify with a full run.

## Style

**Python** — `ruff` and `mypy` are configured in `detector/pyproject.toml` and ship in the `[dev]`
extra. `ruff check src tools` is clean, is what CI runs, and must stay clean. `ruff check tests`
reports 11 findings today — ten import-ordering and one collapsible-if — and runs as a non-blocking
CI step; fixing them is welcome, adding more is not. `detector/aiModule.py` is the original
implementation, kept verbatim as the artifact the rewrite is measured against — it is not linted, not
maintained, and not to be edited.

**Java** — 2-space indent, Lombok (`@Data`, `@Builder`, `@RequiredArgsConstructor` constructor
injection), feature-first packages (`user/`, `event/`, `rawEvent/`, `email/`) each with
`controller/`, `service/`, `model/`, `repository/`; cross-cutting configuration under `core/`.

**JavaScript** — `web/` is React on Vite, with `styled-components` wrappers in
`src/assets/wrappers/`, TanStack Table for the reporting grid, `recharts` for charts, and Redux
Toolkit for the `user` slice only — page-level data is `useState` plus `customFetch` in an effect. Anything the
browser needs from the environment must be `VITE_`-prefixed, and everything so prefixed is baked
into the shipped bundle, so it may never be a secret.

## Comments and commit messages

This codebase explains *why*, at length, and expects the same of new work. A comment that restates
the code is noise; a comment naming the defect a line prevents is the reason the line survives a
future refactor. The module docstrings in `detector/src/worksite_detector/` are the house style.

Commit messages follow the same idea: a `type(scope): imperative summary` first line — `feat`,
`fix`, `test`, `docs`, `refactor`, `chore`, `build`, with `detector`, `engine` or `web` as the scope
— and a body that says what was wrong, what was measured, and what the fix costs. If a number
appears in the message, it should be reproducible from the repository.

## Pull requests

The template asks what changed, why, and how you verified it. Every item on its checklist is a
mistake that has actually been made in this repository and cost real time to find, because in almost
every case nothing failed at the moment it was made.

- One concern per pull request, unless splitting it would produce a commit that does not build.
- Say what you measured. "Fixes flicker" is a claim; "27 detection runs become 4 windows on the
  baseline trace" is a result.
- Run the fast tiers before pushing: `pytest -m "not requires_ultralytics"` in `detector/`,
  `./mvnw test` in `engine/`, `npm test` in `web/`.
- If you touched the detector's rules, run the baseline differential
  (`pytest tests/test_baseline_differential.py`) and say what moved and why.
