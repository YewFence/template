# Rust Project Template

This is an opinionated Rust 2024 project template. It provides a small tested binary crate and keeps local development, CI, dependency auditing, documentation, and releases behind stable mise tasks.

The Rust toolchain is pinned through both mise and `rust-toolchain.toml`. CI follows the same task interface used locally, while GitHub-specific event, permission, cache, artifact, and release wiring stays in workflow YAML.

## Included Tooling

| Capability | Description |
| --- | --- |
| Toolchain and tasks | [mise](https://mise.jdx.dev/) manages development tools, lockfiles, environment overlays, and the stable project task interface |
| Rust quality | Cargo, rustfmt, Clippy, and unit tests cover dependency metadata, formatting, all targets, all features, and optimized builds |
| Security | [cargo-audit](https://github.com/rustsec/rustsec) checks `Cargo.lock` against the RustSec advisory database on dependency changes and a weekly schedule |
| Git hooks | [hk](https://hk.jdx.dev/) runs `mise run fix` and `mise run check` before commits |
| Repository checks | [nllint](https://github.com/suzuki-shunsuke/nllint), [typos](https://github.com/crate-ci/typos), and [betterleaks](https://github.com/betterleaks/betterleaks) provide language-neutral checks |
| GitHub Actions checks | [actionlint](https://github.com/rhysd/actionlint) validates workflows and [pinact](https://github.com/suzuki-shunsuke/pinact) pins actions to immutable commit hashes |
| Documentation | A [VitePress](https://vitepress.dev/) site is managed with [pnpm](https://pnpm.io/) and deployed through GitHub Pages |
| Dependency updates | [Renovate](https://docs.renovatebot.com/) updates Cargo, GitHub Actions, documentation dependencies, and mise tools |
| Releases | [git-cliff](https://git-cliff.org/) prepares changelogs and release pull requests; GitHub Actions publishes Linux, macOS, and Windows archives |

The template uses `mise.lock` and `mise.ci.lock` to pin exact tool versions. A three-day minimum release age is applied by mise, Renovate, and pinact.

## Create A New Project

1. Create a repository from this template, or copy the template files into a new repository.

2. Replace the template repository documents with the generated-project versions.

```bash
cp README.template.md README.md
cp AGENTS.template.md AGENTS.md
rm README.template.md AGENTS.template.md
```

3. Replace the project metadata tokens throughout the repository.

| Token | Meaning |
| --- | --- |
| `{{PROJECT_NAME}}` | Project display name |
| `{{PROJECT_DESCRIPTION}}` | Short project description |
| `{{GITHUB_OWNER}}` | GitHub user or organization |
| `{{REPO_NAME}}` | GitHub repository name |

Use Git to find unresolved project metadata:

```bash
git grep -nE '\{\{[A-Z_]+\}\}'
```

4. Rename the sample crate and binary.

- Change `package.name` in `Cargo.toml`.
- Change `rust_binary_name` in `mise.toml` so release packaging finds the binary.
- Update the `rust_template` crate reference and sample greeting in `src/`.

The stable Rust task interface is ready to use:

| Task | Contract |
| --- | --- |
| `deps:check` | Check dependency metadata and lockfiles without changing them |
| `deps:fix` | Regenerate `Cargo.lock` with Cargo |
| `deps:update` | Update project dependencies intentionally |
| `fmt:check` / `fmt:fix` | Check and apply rustfmt formatting |
| `lint` | Run Clippy across all targets and features with warnings denied |
| `build` / `build:check` | Build the project or perform a compile-only check |
| `test` | Run project tests |
| `audit` | Check project dependencies for known vulnerabilities with `mise -E ci run audit` |

The repository-level tasks such as `newline:*`, `typos:*`, `leaks:check`, `actions:*`, `docs:*`, `check`, and `fix` are also fully implemented.

5. Install the project tools and Git hooks.

```bash
mise trust
mise install
mise run hooks:install
mise run check
```

6. Replace the sample code and project-specific `[PLACEHOLDER]` documentation with the real product behavior. The release workflow already packages the configured binary for Linux x86_64/aarch64, macOS x86_64/aarch64, and Windows x86_64.

This new-project setup is currently a manual workflow. It is separate from adopting the engineering setup in an existing repository.

## Adopt In An Existing Repository

Apply the committed template snapshot to a clean existing Git repository:

```bash
./scripts/apply-template /path/to/repository
```

The script creates an uncommitted Git merge so the result can be reviewed or aborted as one operation. New template files are staged, while paths that already exist in the target are left as merge conflicts for deliberate resolution. The script never commits on behalf of the target repository.

Repository-owned files require stricter handling:

- `.gitignore` keeps all existing rules and receives only missing template rules.
- Root `README*`, `AGENTS*`, license, copyright notice, and `COPYING*` files are not applied.
- `.gitattributes`, `.gitmodules`, and CODEOWNERS files are not applied because they can change checkout behavior, external content, or repository permissions.

Resolve any reported conflicts, review the staged changes, and then commit them normally. Pay particular attention to `.github/workflows`, `mise.toml`, lockfiles, `renovate.json`, and release configuration: these can execute code, alter CI or release behavior, or replace project-specific dependency settings. Do not line-merge generated lockfiles; choose the appropriate dependency metadata and regenerate each lockfile with its native tool. To discard the complete operation, run `git merge --abort`.

After resolving the merge, replace the `{{PROJECT_NAME}}`, `{{PROJECT_DESCRIPTION}}`, `{{GITHUB_OWNER}}`, and `{{REPO_NAME}}` tokens introduced by template files. When adopting into an existing Rust binary, align `package.name`, `rust_binary_name`, and the existing crate layout deliberately.

The application transaction is a Git merge even in a colocated Jujutsu repository. Detached Git HEAD is supported, but finish or abort this transaction with Git before continuing normal `jj` operations so no pending `MERGE_HEAD` is left behind.

## GitHub Repository Setup

After pushing the generated project to GitHub:

1. Go to `Settings` > `Actions` > `General` > `Workflow permissions`, then enable `Allow GitHub Actions to create and approve pull requests`. The release preparation workflow needs this repository setting in addition to its declared `pull-requests: write` permission.
2. Go to `Settings` > `Pages` > `Build and deployment`, then set `Source` to `GitHub Actions`.
3. Install and configure the official [Renovate GitHub App](https://github.com/apps/renovate).

## Common Commands

```bash
# List all available tasks
mise tasks

# Run read-only repository and project checks
mise run check

# Apply safe automatic fixes
mise run fix

# Build the project documentation
mise run docs:build

# Update and pin GitHub Actions
mise run actions:update
```

See [mise.toml](mise.toml), [mise.ci.toml](mise.ci.toml), and the [Development Guide](CONTRIBUTING.md) for the complete task definitions.

## Release Workflow

The release policy uses Conventional Commits through git-cliff.

When commits land on `main`, [Prepare Release](.github/workflows/prepare-release.yml) calculates the next semantic version, updates `Cargo.toml` and `Cargo.lock`, generates or prepends `CHANGELOG.md`, updates the fixed `release` branch, and creates or updates a pull request back to `main`. The pull request records the exact `main` commit used to prepare the release so stale release pull requests are rejected.

[Release](.github/workflows/release.yml) publishes from an existing `v*` tag, from a merged `release` pull request, or from a manual dispatch that names an existing tag. It validates semantic version tags, builds and packages the configured Rust binary across the platform matrix, generates release notes, creates the tag when required, and uploads the archives to GitHub Releases.

The reusable release helpers live in `mise.ci.toml`. For example:

```bash
mise -E ci run release:version
mise -E ci run release:version:update 1.2.3
mise -E ci run release:tag
RELEASE_TAG=v1.2.3 mise -E ci run release:notes
RELEASE_TAG=v1.2.3 mise -E ci run release:changelog
RELEASE_TAG=v1.2.3 RELEASE_TARGET=x86_64-unknown-linux-gnu RELEASE_PLATFORM=linux-x86_64 mise -E ci run release:package
```

## License

[MIT License](LICENSE)
