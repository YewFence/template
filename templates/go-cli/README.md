# Go CLI Template

This is a ready-to-use Go CLI project template. It uses [Cobra](https://github.com/spf13/cobra) for command organization, [mise](https://github.com/jdx/mise) for toolchain and task management, and includes a [VitePress documentation site](./docs), GitHub Actions [continuous integration](.github/workflows/ci.yml), [documentation publishing](.github/workflows/docs.yml), [Renovate dependency updates](./renovate.json), simple linting, and an [automated release workflow](#release-workflow).

## Requirements

Install [mise](https://github.com/jdx/mise) first.

Other development tools are declared in [mise.toml](mise.toml). Run `mise install` to install them.

This template uses [mise.lock](mise.lock) to pin the exact versions of the tools declared in `mise.toml`.

## Included Tooling

| Capability | Description |
| --- | --- |
| CLI framework | Cobra is wired in with a root command, a `version` subcommand, shell completion commands, and a `cmd/your-cli` executable entrypoint |
| Toolchain | Go, Node, pnpm, actions-up, golangci-lint, and related tools are managed through `mise` |
| Development tasks | Reusable mise tasks include `deps:update`, `fix`, `check`, `build`, and `cli`; see [mise.toml](mise.toml) for the full list |
| Useful default lint rules | Default checks include `go mod tidy` verification, golangci-lint, [newline lint](https://github.com/suzuki-shunsuke/nllint), and [spell checking](https://github.com/crate-ci/typos) |
| Agent instructions | `AGENTS.template.md` becomes `AGENTS.md` after initialization. It tells future development agents to run `mise run check` after Go code changes and notes that the generated project is still early enough to avoid backward-compatibility constraints |
| Documentation site | The `docs` directory includes a VitePress documentation site and a GitHub Pages workflow |
| CI checks | GitHub Actions run `mise run check`, audit dependencies, and build the documentation |
| Dependency updates | `renovate.json` configures Renovate for GitHub Actions, npm, Go modules, and mise tool updates. Connect the official [Renovate GitHub App](https://github.com/apps/renovate) to enable pull requests |
| Release workflow | `git-cliff` prepares release pull requests from `main` updates, while pushed `v*` tags and merged `release` pull requests publish GitHub Releases |
| Security | [pinact](https://github.com/suzuki-shunsuke/pinact) pins GitHub Actions versions to commit hashes. A 3-day minimum release age is configured for [Renovate](./renovate.json#L10), [pinact](https://github.com/suzuki-shunsuke/pinact#minimum-release-age-cooldown--min-age--verify-min-age) through environment variables in [mise.toml](./mise.toml#L27), and [mise](./mise.toml#L4). CI runs [govulncheck](https://golang.org/x/vuln/cmd/govulncheck) to check for dependency vulnerabilities |

## Quick Start

1. Click `Use this template` to create a new repository, or clone this repository directly.

```bash
git clone https://github.com/YewFence/go-cli-template.git your-cli
cd your-cli
```

2. Trust the mise configuration and install development tools.

```bash
mise trust
mise install
```
3. Run the initialization task.

```bash
mise run init
```

This task asks for the Go module path, command name, GitHub owner or organization, repository name, and project description. It then replaces the template content, removes the template repository origin, and reinitializes the Git history in the current directory so the cloned project starts from a clean `main` branch.

Initialization also replaces this repository's `AGENTS.md` with the generated project's `AGENTS.template.md`. The preset agent prompt assumes early-stage development, requires `mise run check` after Go changes, and can be adjusted once your project moves into stable maintenance.

The generated project keeps `renovate.json`. To enable dependency update pull requests, install and configure the official [Renovate GitHub App](https://github.com/apps/renovate) for the generated repository.

The generated project is intentionally shaped as a single-command CLI. The executable entrypoint lives under `cmd/<command-name>`, and the mise build, run, install, and release tasks use `./cmd/...` so Go derives the binary name from that entrypoint directory. If you add more executable entrypoints under `cmd/`, adjust those tasks and the release packaging logic at the same time.

After pushing the generated project to GitHub, update these repository settings:

1. Go to `Settings` > `Actions` > `General` > `Workflow permissions`, then enable `Allow GitHub Actions to create and approve pull requests` under `Choose whether GitHub Actions can create pull requests or submit approving pull request reviews`. The release preparation workflow already requests `pull-requests: write`, but this repository setting must also allow `GITHUB_TOKEN` to create the release pull request.
2. Go to `Settings` > `Pages` > `Build and deployment`, then set `Source` to `GitHub Actions`. The documentation workflow already requests `pages: write` and `id-token: write`, but Pages must use GitHub Actions as its deployment source for `actions/deploy-pages` to publish the built documentation site.

You can also pass all values at once, which is useful for scripted project creation.

```bash
mise run init -- \
  --module github.com/you/your-cli \
  --name your-cli \
  --owner you \
  --repo your-cli \
  --description "Your CLI description"
```

Initialization replaces these template defaults.

| Template default | Replaced with |
| --- | --- |
| `github.com/example/your-cli` | Your Go module path |
| `your-cli` | Your command name |
| `example` | Your GitHub owner or organization |
| `Your CLI description` | Your project description |

4. Clean up template-only files.

After initialization is complete and the replacement result looks correct, remove the template-only initialization tool. The initialization task removes its own `mise.toml` task entry automatically.

```bash
rm -rf tools/init-template
```

## Apply To An Existing Project

If you already have a Go project and only want to reuse this template's project configuration, run the existing-project apply tool. It does not modify application code, `go.mod`, README, Git origin, or Git history. It only overwrites `mise.toml`, `renovate.json`, `.gitignore`, and `.github/workflows`, and downloads the template documentation site only when the current project does not already have a `docs` directory.

Before running it, make sure the Git working tree is clean. The tool also asks you to type `yes` before continuing. After it finishes, use `git diff` to review the changes and keep or adjust them as needed. To enable dependency update pull requests, install and configure the official [Renovate GitHub App](https://github.com/apps/renovate) for the repository.

```bash
go run github.com/YewFence/go-cli-template/tools/apply-existing@latest
git diff
```

Pass `--ref` to download template files from a specific branch or commit.

```bash
go run github.com/YewFence/go-cli-template/tools/apply-existing@latest --ref main
```

You can also download the single file first and run it locally, which is useful when you want to review the source before executing it.

```bash
tmp="$(mktemp -d)"
curl -fsSL https://raw.githubusercontent.com/YewFence/go-cli-template/main/tools/apply-existing/main.go -o "$tmp/apply-existing.go"
go run "$tmp/apply-existing.go"
```

## Release Workflow Structure

This template uses `git-cliff` as the release version and changelog engine, and keeps the platform-specific automation directly in GitHub Actions workflow files.

When commits land on `main`, [.github/workflows/prepare-release.yml](.github/workflows/prepare-release.yml) calculates the next semantic version with `git cliff --bumped-version`, updates `CHANGELOG.md` with unreleased changes for that tag, pushes a fixed `release` branch, and creates or updates a pull request back to `main`. The fixed branch name keeps the release path easy to recognize, and the generated pull request makes the changelog reviewable before anything is published.

[.github/workflows/release.yml](.github/workflows/release.yml) is the only workflow that publishes releases. It runs when a local `v*` tag is pushed, so manual tag-driven releases stay supported, and it also runs when the `release` pull request is merged into `main`. In the merged release pull request path, the workflow recalculates the same `git-cliff` version, creates the tag in that same run, builds release artifacts, generates release notes with `git-cliff`, and publishes the GitHub Release. Creating the tag and publishing the release in the same workflow keeps the merged release PR path reliable, because tags pushed by the workflow's `GITHUB_TOKEN` do not start another tag-triggered workflow run.

The release pull request body includes a hidden `release-base-sha` marker that records the `main` commit used to generate the changelog. When the release pull request is merged, the release workflow compares that marker with the merged release commit's first parent, which rejects stale release pull requests that were generated before newer `main` commits landed. The workflow also checks that the first semantic version found in `CHANGELOG.md` matches the resolved release tag.

Release runs are serialized by event and ref, and manually dispatched releases require tags in `vMAJOR.MINOR.PATCH` form with an optional prerelease suffix. Tag-driven and release pull request releases with a prerelease suffix are published as GitHub prereleases, while manually dispatched releases use the explicit `prerelease` input.

After a manual release is published, a separate low-privilege cleanup job looks for an open `release` to `main` pull request that still matches the published tag, comments on it, renames it with an `[autoclosed]` suffix, and closes it.

The release automation is intentionally hand-rolled instead of delegated to a GitHub-only release manager such as [release-please](https://github.com/googleapis/release-please). The moving pieces are small and explicit: `git-cliff` owns version and changelog generation, `gh` owns pull request operations, and the release workflow owns tagging, building, and publishing. Keeping those responsibilities visible makes it easier to port the same release model to another forge such as Forgejo later.

The reusable release helpers live in `mise.ci.toml`. Run them with `MISE_ENV=ci`, for example `MISE_ENV=ci mise run release:version` to print the next version, `MISE_ENV=ci mise run release:tag` to print the next tag, `MISE_ENV=ci RELEASE_TAG=v1.2.3 mise run release:notes` to preview release notes, and `MISE_ENV=ci RELEASE_TAG=v1.2.3 mise run release:changelog` to update `CHANGELOG.md`.

## Development From This Template

See [README.template.md](README.template.md) and the [Development Guide](CONTRIBUTING.md) for details.

## License

[MIT License](LICENSE)
