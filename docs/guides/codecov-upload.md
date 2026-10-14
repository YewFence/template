# Uploading Coverage to Codecov

The optional `codecov-upload` template capability adds a `mise run coverage` task and a single Codecov upload workflow triggered by pull requests and the default branch. It is disabled by default for the `common`, `python`, `go-cli`, `rust`, and `node-project` template profiles.

## Prerequisites

The generated workflow contract targets public GitHub repositories. Before relying on pull request uploads, enable tokenless uploads in the Codecov organization settings as described in [Codecov's token documentation](https://docs.codecov.com/docs/codecov-tokens#uploading-without-a-token).

The template does not create or read a long-lived `CODECOV_TOKEN`. Private repositories require project-specific authentication and workflow changes after instantiation; that configuration is outside the capability contract.

## Workflow Boundaries

All coverage runs live in a single `.github/workflows/coverage.yml` workflow, so pull requests and the default branch share one job structure instead of duplicating coverage steps across CI jobs. The workflow triggers on pushes to `main`, pull requests targeting `main`, and manual dispatches restricted to the `main` ref; both push and pull request triggers use path filters, so documentation-only or tooling-only changes no longer run a full test sweep just to refresh coverage.

The single coverage job always uploads exactly one explicit report file with automatic report search disabled and fails when report generation or upload fails. It uses the ordinary `pull_request` event and never `pull_request_target`, `override_branch`, or `override_pr`; Codecov Action derives commit and pull request metadata from the GitHub event and handles the fork-specific tokenless path. Authentication switches on the event name: `use_oidc` is enabled for default-branch pushes and manual dispatches, while pull requests (including forks) fall back to tokenless uploads. The job therefore declares `id-token: write`, which GitHub downgrades to read-only for fork pull requests, so forks can never mint the repository's OIDC token. Its concurrency group is `coverage-${{ github.ref }}` with cancellation enabled, so a newer run supersedes an older one on the same ref.

The workflow does not set `skip_validation`; Codecov Action keeps its default system-dependency checks while mise owns the supplied CLI's version and integrity state. The template does not define Codecov thresholds, flags, components, carryforward rules, badges, or `codecov.yml` policy.

The workflow owns authentication and upload behavior. A profile `coverage_adapter` owns only its cache and report-generation task; it runs as the `coverage` step and exposes exactly one report path to the shared uploader. The `common` adapter is intentionally a failing placeholder: it prints the replacement instruction and exits non-zero until you provide a real coverage command. It never creates an empty or synthetic report.

## Tool Versions

The template declares `codecov/codecov-action@v7` and the Codecov CLI `11` compatibility lines. During project bootstrap, pinact locks the Action to a commit digest and mise locks the CLI to a concrete version. The workflow resolves the mise-installed `codecovcli` executable and supplies it to the Action through the `binary` input.

## Coverage Reports

The profile adapters generate these files in the repository root:

| Template | Command behavior | Report |
| --- | --- | --- |
| `common` | Placeholder that must be replaced with the project's coverage command | `coverage.xml` |
| `go-cli` | `go test` with atomic coverage across all packages | `coverage.out` |
| `rust` | `cargo llvm-cov` across the workspace and all features | `lcov.info` |
| `node-project` | `vitest` with the v8 coverage provider | `coverage/lcov.info` |

For a `common` project, replace the placeholder `coverage` task before expecting CI to pass. Go, Rust, and Node projects can use the supplied adapter or replace it with project-specific coverage behavior while preserving the report path expected by the workflow.

## Bootstrap and Verify

After project instantiation, generate the project's mise locks and Action digests through the normal bootstrap flow:

```bash
mise -E ci lock
mise install --locked
mise run actions:update
```

Run `mise run coverage` locally to verify that the expected report is produced. The template monorepo validates workflow structure and report generation without uploading to a real Codecov project. The first adopting public repository should confirm tokenless uploads for same-repository and fork pull requests, default-branch OIDC, commit and PR association, and the resulting Codecov status or comment.
