# common Template

A language-agnostic project template: the full repository automation with no language toolchain committed. Project-specific tasks (dependency management, tests, formatting, lint, build) ship as `[PLACEHOLDER]` stubs for you to fill in.

Rendered default-capability preview: [`templates/common/`](../../templates/common/).

## What's Included

- The complete shared tooling: mise-managed tasks, GitHub Actions CI, git-cliff release automation, Renovate, and hk Git hooks — see the [root README](../../README.md#features)
- Language-neutral checks that work out of the box: nllint newline lint, typos spell checking, betterleaks secret scanning, and actionlint workflow lint

## Capabilities

| Capability | Default | What it adds |
| --- | --- | --- |
| `docs-site` | enabled | VitePress documentation site with a GitHub Pages deployment workflow |
| `codecov-upload` | disabled | Replaceable coverage task plus PR and default-branch Codecov uploads — see the [Codecov guide](../../docs/guides/codecov-upload.md) |

## Required Metadata

`init-project` asks for these fields (or pass them as the matching CLI options):

- `project_name` — project display name
- `description` — one-line project description
- `github_owner` — GitHub user or organization that will own the repository
- `repo_name` — GitHub repository name

## See Also

- [Usage guide](../../docs/guides/use-template.md)
- [Codecov upload guide](../../docs/guides/codecov-upload.md)
- [CLI reference](../../docs/reference/cli.md)
