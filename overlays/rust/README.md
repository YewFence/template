# rust Template

A Rust CLI project template with a locked-by-default Cargo workflow and a mise-managed toolchain.

Rendered default-capability preview: [`templates/rust/`](../../templates/rust/).

## What's Included

- The complete shared tooling: mise-managed tasks, GitHub Actions CI, git-cliff release automation, Renovate, and hk Git hooks — see the [root README](../../README.md#features)
- Rust CLI skeleton (`src/main.rs` + `src/lib.rs`) with a pinned `rust-toolchain.toml`; mise provides Rust with clippy and rustfmt
- Locked-by-default Cargo tasks: `test`, `lint` (clippy with warnings denied), `build`/`build:check`, and `deps:*` all run with `--locked`
- Dependency audit: `cargo audit --deny warnings`
- Multi-platform release builds: Linux x86_64/aarch64, macOS x86_64/aarch64, and Windows x86_64

## Capabilities

| Capability | Default | What it adds |
| --- | --- | --- |
| `docs-site` | enabled | VitePress documentation site with a GitHub Pages deployment workflow |
| `crates-io-publish` | disabled | crates.io publishing with trusted publishing: package checks in CI and a publish job on release — see the [crates.io publishing guide](../../docs/guides/rust-crates-io-publishing.md) |
| `codecov-upload` | disabled | Rust coverage report plus PR and default-branch Codecov uploads — see the [Codecov guide](../../docs/guides/codecov-upload.md) |

## Required Metadata

`init-project` asks for these fields (or pass them as the matching CLI options):

- `project_name` — project display name
- `description` — one-line project description
- `github_owner` — GitHub user or organization that will own the repository
- `repo_name` — GitHub repository name
- `cargo_package` — Cargo package name
- `binary_name` — compiled binary name

## See Also

- [Usage guide](../../docs/guides/use-template.md)
- [Codecov upload guide](../../docs/guides/codecov-upload.md)
- [CLI reference](../../docs/reference/cli.md)
