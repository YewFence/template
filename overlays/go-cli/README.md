# go-cli Template

A Go CLI project template with a Cobra skeleton wired in and a locked, mise-managed toolchain.

Rendered default-capability preview: [`templates/go-cli/`](../../templates/go-cli/).

## What's Included

- The complete shared tooling: mise-managed tasks, GitHub Actions CI, git-cliff release automation, Renovate, and hk Git hooks — see the [root README](../../README.md#features)
- Cobra CLI skeleton: root command, a `version` subcommand, shell completion wiring, and the entrypoint at `cmd/<binary_name>`
- Go tasks: `mod:tidy`, `deps:update`, `test`, gofmt formatting and golangci-lint (with `asciicheck`) via `fmt:*`/`lint`, `cli`, `cli:install`, and `build` with version injection through `-ldflags`
- Dependency audit: `govulncheck` plus `go mod verify`
- Multi-platform release builds (GOOS/GOARCH matrix) packaged as archives on each GitHub Release

## Capabilities

| Capability | Default | What it adds |
| --- | --- | --- |
| `docs-site` | enabled | VitePress documentation site with a GitHub Pages deployment workflow |
| `container-image-publish` | disabled | Multi-platform container image built with ko and published to GHCR after each release — see the [container image publishing guide](../../docs/guides/go-cli-container-image-publishing.md) |
| `codecov-upload` | disabled | Coverage task and CI job uploading coverage to Codecov |

## Required Metadata

`init-project` asks for these fields (or pass them as the matching CLI options):

- `project_name` — project display name
- `description` — one-line project description
- `github_owner` — GitHub user or organization that will own the repository
- `repo_name` — GitHub repository name
- `go_module` — Go module path (e.g. `github.com/you/your-cli`)
- `binary_name` — compiled binary name; also the `cmd/` entrypoint directory

## See Also

- [Usage guide](../../docs/guides/use-template.md)
- [CLI reference](../../docs/reference/cli.md)
