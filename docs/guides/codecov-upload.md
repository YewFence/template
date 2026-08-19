# Uploading Coverage to Codecov

The optional `codecov-upload` template capability adds a `mise run coverage` task and Codecov uploads for pull requests and the default branch. It is disabled by default for the `common`, `go-cli`, and `rust` template profiles.

## Prerequisites

The generated workflow contract targets public GitHub repositories. Before relying on pull request uploads, enable tokenless uploads in the Codecov organization settings as described in [Codecov's token documentation](https://docs.codecov.com/docs/codecov-tokens#uploading-without-a-token).

The template does not create or read a long-lived `CODECOV_TOKEN`. Private repositories require project-specific authentication and workflow changes after instantiation; that configuration is outside the capability contract.

## Workflow Boundaries

Pull request coverage runs as a job in `.github/workflows/ci.yml`. It uses the ordinary `pull_request` event, has only `contents: read`, and uploads without a token. It does not use OIDC, repository secrets, `pull_request_target`, `override_branch`, or `override_pr`. Codecov Action derives commit and pull request metadata from the GitHub event and handles the fork-specific tokenless path.

Default-branch coverage runs independently in `.github/workflows/coverage.yml`. Pushes to `main` and manual dispatches using the `main` ref regenerate the report and upload with Codecov OIDC. Only this trusted job receives `id-token: write`; it never consumes artifacts produced by a pull request workflow. Its concurrency group is `coverage-${{ github.ref }}` with cancellation enabled, so a newer `main` run supersedes an older one.

Both paths upload exactly one explicit report file with automatic report search disabled and fail the job when report generation or upload fails. The workflow does not set `skip_validation`; Codecov Action keeps its default system-dependency checks while mise owns the supplied CLI's version and integrity state. The template does not define Codecov thresholds, flags, components, carryforward rules, badges, or `codecov.yml` policy.

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

For a `common` project, replace the placeholder `coverage` task before expecting CI to pass. Go and Rust projects can use the supplied adapter or replace it with project-specific coverage behavior while preserving the report path expected by the workflow.

## Bootstrap and Verify

After project instantiation, generate the project's mise locks and Action digests through the normal bootstrap flow:

```bash
mise -E ci lock
mise install --locked
mise run actions:update
```

Run `mise run coverage` locally to verify that the expected report is produced. The template monorepo validates workflow structure and report generation without uploading to a real Codecov project. The first adopting public repository should confirm tokenless uploads for same-repository and fork pull requests, default-branch OIDC, commit and PR association, and the resulting Codecov status or comment.
