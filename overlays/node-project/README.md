# node-project Template

A TypeScript library template: a src-layout Node package with aube, vitest, oxlint, oxfmt, and tsdown. The toolchain and repository automation are managed by mise; project dependencies live in `package.json` and are locked by aube.

Rendered default-capability preview: [`templates/node-project/`](../../templates/node-project/).

## What's Included

- The complete shared tooling: mise-managed tasks, GitHub Actions CI, git-cliff release automation, Renovate, and hk Git hooks — see the [root README](../../README.md#features)
- Language checks that work out of the box: oxlint linting, oxfmt formatting, tsc type checks, tsdown builds, and vitest tests via `aube exec`
- `aube audit` security audits against the npm registry advisory database

## Capabilities

| Capability | Default | What it adds |
| --- | --- | --- |
| `docs-site` | enabled | VitePress documentation site with a GitHub Pages deployment workflow, installed with aube |
| `codecov-upload` | disabled | vitest coverage task plus PR and default-branch Codecov uploads — see the [Codecov guide](../../docs/guides/codecov-upload.md) |
| `npm-publish` | disabled | npm publishing with trusted publishing: package checks in CI and a publish job on release — see the [npm publishing guide](../../docs/guides/node-npm-publishing.md) |

## Required Metadata

`init-project` asks for these fields (or pass them as the matching CLI options):

- `project_name` — project display name
- `description` — one-line project description
- `github_owner` — GitHub user or organization that will own the repository
- `repo_name` — GitHub repository name
- `node_package` — Node package source directory name under `src/`

## See Also

- [Usage guide](../../docs/guides/use-template.md)
- [Codecov upload guide](../../docs/guides/codecov-upload.md)
- [npm publishing guide](../../docs/guides/node-npm-publishing.md)
- [CLI reference](../../docs/reference/cli.md)
