# Engineering Project Template

This is an opinionated, language-neutral project template. It keeps reusable engineering workflows stable while leaving project-language behavior as explicit `[PLACEHOLDER]` mise tasks that are replaced once when a project is created.

The template intentionally does not detect, select, or switch programming languages. A generated project chooses its language and toolchain during initial setup, then owns those choices normally.

## Included Tooling

| Capability | Description |
| --- | --- |
| Toolchain and tasks | [mise](https://mise.jdx.dev/) manages development tools, lockfiles, environment overlays, and the stable project task interface |
| Git hooks | [hk](https://hk.jdx.dev/) runs `mise run check` before commits and suggests `mise run fix` when checks fail |
| Repository checks | [nllint](https://github.com/suzuki-shunsuke/nllint), [typos](https://github.com/crate-ci/typos), and [betterleaks](https://github.com/betterleaks/betterleaks) provide language-neutral checks |
| GitHub Actions checks | [actionlint](https://github.com/rhysd/actionlint) validates workflows and [pinact](https://github.com/suzuki-shunsuke/pinact) pins actions to immutable commit hashes |
| Documentation | A [VitePress](https://vitepress.dev/) site is managed with [pnpm](https://pnpm.io/) and deployed through GitHub Pages |
| Dependency updates | [Renovate](https://docs.renovatebot.com/) updates GitHub Actions, documentation dependencies, and mise tools |
| Releases | [git-cliff](https://git-cliff.org/) prepares changelogs and release pull requests; GitHub Actions publishes tags and GitHub Releases |

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

Use Git to find unresolved metadata and task placeholders:

```bash
git grep -nE '\{\{[A-Z_]+\}\}|\[PLACEHOLDER\]'
```

4. Replace every `[PLACEHOLDER]` task in `mise.toml` with the command for the selected language and toolchain. The stable task interface includes:

| Task | Contract |
| --- | --- |
| `deps:check` | Check dependency metadata and lockfiles without changing them |
| `deps:fix` | Normalize dependency metadata and lockfiles |
| `deps:update` | Update project dependencies intentionally |
| `fmt:check` / `fmt:fix` | Check and apply project-language formatting |
| `lint` | Run project-language static analysis |
| `build` / `build:check` | Build the project or perform a compile-only check |
| `test` | Run project tests |
| `audit` | Check project dependencies for known vulnerabilities |

The repository-level tasks such as `newline:*`, `typos:*`, `leaks:check`, `actions:*`, `docs:*`, `check`, and `fix` already have real implementations.

5. Add language-specific tools through mise, update Renovate managers, and extend `.gitignore` for the selected language. Use mise and the language package manager to regenerate lockfiles; do not edit lockfiles manually.

6. Install the project tools and Git hooks.

```bash
mise trust
mise install
mise run hooks:install
mise run check
```

7. Decide whether the project needs release assets. The shared release workflow publishes a tag, generated notes, and a GitHub Release without attachments. Projects that publish binaries, packages, SBOMs, or checksums should add their own build and packaging jobs and implement `release:package`.

This new-project setup is currently a manual workflow. It is separate from adopting the engineering setup in an existing repository.

## Adopt In An Existing Repository

Apply the committed template snapshot to a clean existing Git repository:

```bash
./scripts/apply-template /path/to/repository
```

The script applies the template as staged changes so the result can be reviewed or discarded as one operation without attaching the template's Git history to the target. New template files are staged, while differing paths that already exist in the target are left as index conflicts for deliberate resolution. Target-side content remains in the worktree where possible; inspect the index conflict instead of expecting conflict-marker files. The script never commits on behalf of the target repository.

Repository-owned files require stricter handling:

- `.gitignore` keeps all existing rules and receives only missing template rules.
- Root `README*`, `AGENTS*`, license, copyright notice, and `COPYING*` files are not applied.
- `.gitattributes`, `.gitmodules`, and CODEOWNERS files are not applied because they can change checkout behavior, external content, or repository permissions.

Resolve any reported conflicts, review the staged changes, and then commit them normally. Include the `Template-Commit` trailer reported by the script if the commit should retain exact template provenance. Pay particular attention to `.github/workflows`, `mise.toml`, lockfiles, `renovate.json`, and release configuration: these can execute code, alter CI or release behavior, or replace project-specific dependency settings. Do not line-merge generated lockfiles; choose the appropriate dependency metadata and regenerate each lockfile with its native tool. Because the target must be clean before applying the template, the complete operation can be discarded with `git reset --hard HEAD`.

After resolving the application conflicts, replace the `{{PROJECT_NAME}}`, `{{PROJECT_DESCRIPTION}}`, `{{GITHUB_OWNER}}`, and `{{REPO_NAME}}` tokens introduced by template files, then replace any applicable `[PLACEHOLDER]` mise tasks with the target project's existing commands.

Detached Git HEAD in a colocated Jujutsu repository is supported. Resolve and commit the staged application, or discard it with Git, before continuing normal `jj` operations.

## GitHub Repository Setup

After pushing the generated project to GitHub:

1. Go to `Settings` > `Actions` > `General` > `Workflow permissions`, then enable `Allow GitHub Actions to create and approve pull requests`. The release preparation workflow needs this repository setting in addition to its declared `pull-requests: write` permission.
2. Go to `Settings` > `Pages` > `Build and deployment`, then set `Source` to `GitHub Actions`.
3. Install and configure the official [Renovate GitHub App](https://github.com/apps/renovate), then add the manager and package rules for the selected project language.

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

The shared release policy is language-neutral and uses Conventional Commits through git-cliff.

When commits land on `main`, [Prepare Release](.github/workflows/prepare-release.yml) calculates the next semantic version, generates or prepends `CHANGELOG.md`, updates the fixed `release` branch, and creates or updates a pull request back to `main`. The pull request records the exact `main` commit used to generate the changelog so stale release pull requests are rejected.

[Release](.github/workflows/release.yml) publishes from an existing `v*` tag, from a merged `release` pull request, or from a manual dispatch that names an existing tag. It validates semantic version tags, generates release notes, creates the tag when the release pull request path requires it, and publishes a GitHub Release without project-specific assets.

The reusable release helpers live in `mise.ci.toml`. For example:

```bash
mise -E ci run release:version
mise -E ci run release:tag
RELEASE_TAG=v1.2.3 mise -E ci run release:notes
RELEASE_TAG=v1.2.3 mise -E ci run release:changelog
```

## License

[MIT License](LICENSE)
