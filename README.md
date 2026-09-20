# YewFence Project Templates

Project templates for bootstrapping new repositories: a language-agnostic base, a Go CLI, and a Rust CLI. Each template renders a complete project — mise toolchain and tasks, GitHub Actions CI, release automation, and an optional docs site — instantiated for your project identity by a single CLI command.

## Features

| Feature | Description |
| --- | --- |
| Project templates | Three profiles — `common` (language-agnostic), `go-cli` (Go + Cobra), and `rust` (Rust CLI) — each with its own optional capabilities |
| One-command instantiation | `init-project` interactively collects capabilities and metadata, creates the initial commit, and stages your project |
| Toolchain management | Every development tool is managed through mise and locked per project |
| Task runner | Ready-made mise tasks: `check`, `fix`, `build`, `test`, `deps:update`, `hooks:install`, and more |
| CI checks | GitHub Actions run the project checks, audit dependencies, and build the docs site |
| Release automation | git-cliff prepares release PRs from `main`; pushed `v*` tags and merged release PRs publish GitHub Releases with pre-built archives |
| Dependency updates | Renovate config covering GitHub Actions, language dependencies, and mise tools |
| Docs site | Optional VitePress documentation site deployed to GitHub Pages (`docs-site` capability, enabled by default) |
| Coverage | Optional Codecov upload (`codecov-upload` capability) — see the [Codecov guide](docs/guides/codecov-upload.md) |
| Security | pinact pins GitHub Actions to commit hashes, a minimum release age applies to tool and action updates, and CI audits dependencies for vulnerabilities and leaked secrets |

## Templates

| Template | Purpose | Notable capabilities |
| --- | --- | --- |
| [`common`](overlays/common/README.md) | Language-agnostic starting point with full repository automation | `docs-site`, `codecov-upload` |
| [`go-cli`](overlays/go-cli/README.md) | Go CLI with a Cobra skeleton and multi-platform builds | plus `container-image-publish` (ko → GHCR) |
| [`rust`](overlays/rust/README.md) | Rust CLI with a locked-by-default Cargo workflow | plus `crates-io-publish` (trusted publishing) |

Each template also renders a complete default-capability preview under [`templates/`](templates/).

## Quick Start

Requirements: Git and [uv](https://docs.astral.sh/uv/). Generated projects expect [mise](https://mise.jdx.dev/).

### Create a New Project

```bash
mkdir my-project
cd my-project
git init

uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  init-project \
  --ref main \
  --template common \
  --interactive \
  .
```

The tool asks which capabilities to enable and for the template's metadata fields (GitHub owner, repository name, description, and template-specific fields), confirms a summary, creates the initial commit, and stages the instantiated project. Afterwards, generate and commit the project's own dependency lock state and GitHub Action digests:

```bash
mise trust
mise -E ci lock
mise install --locked
mise run deps:update
mise run docs:install
mise run actions:update
mise run hooks:install
mise run check
```

### Apply to an Existing Repository

The target must be a clean Git repository with at least one commit:

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  apply-template \
  --ref main \
  --template go-cli \
  --interactive \
  .
```

Template changes are staged to the Git index only — review and commit them yourself.

### Export for a Manual Upgrade

There is no repeated-apply or upgrade contract. Export the newest ref into a temporary directory, then diff and copy selectively:

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  export-template \
  --ref main \
  --template rust \
  --interactive \
  ./rust-template-main
```

### Query Capabilities

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  list-template-capabilities \
  --ref main \
  --template rust
```

## Design

Editable sources live in `shared/` and `overlays/`; `templates/<name>/` holds the complete, self-contained default preview generated from them, so common behavior is declared once and shared by every template. Each template declares a capability profile: optional behavior is selected when the template is applied, not edited in afterwards. Applying always re-renders from the selected ref's sources. See [docs/architecture/monorepo.md](docs/architecture/monorepo.md) for the full design.

## Documentation

- [Agent skill](skills/use-template/SKILL.md) — hand the whole flow to a coding agent: profile and capability selection, instantiation, conflict resolution, and bootstrap to a passing check
- [Usage guide](docs/guides/use-template.md) — preconditions, conflict handling, non-interactive usage, and the Bash fallback
- [CLI reference](docs/reference/cli.md) — every command and option, generated from the tool's `--help` output
- [crates.io publishing guide](docs/guides/rust-crates-io-publishing.md) and [container image publishing guide](docs/guides/go-cli-container-image-publishing.md) — for the respective capabilities
- Maintenance rules and the full documentation index: [AGENTS.md](AGENTS.md) and [docs/](docs/README.md)

## License

[MIT License](LICENSE)
