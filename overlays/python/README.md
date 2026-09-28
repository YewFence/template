# Python Template

A Python project starting point based on the common repository automation, with mise-managed Python, uv, Ruff, and ty. Includes a buildable package, a pytest smoke test, dependency audit, and ready-to-run formatting, linting, and type-checking tasks.

Rendered default-capability preview: [`templates/python/`](../../templates/python/).

## Capabilities

| Capability | Default | What it adds |
| --- | --- | --- |
| `docs-site` | enabled | VitePress documentation site with a GitHub Pages deployment workflow |
| `codecov-upload` | disabled | pytest-cov coverage report plus PR and default-branch Codecov uploads |

## Required Metadata

`init-project` asks for the common fields `project_name`, `description`, `github_owner`, and `repo_name`, plus `python_package`, the importable package identifier used under `src/`.

After instantiation, generate the project's own dependency state with `mise -E ci lock`, `mise install --locked`, `mise run deps:fix`, and `mise run actions:update` (and `mise run docs:lock` when docs are enabled). Commit the generated lockfiles and pinned workflows.

## See Also

- [Usage guide](../../docs/guides/use-template.md)
- [Codecov upload guide](../../docs/guides/codecov-upload.md)
- [CLI reference](../../docs/reference/cli.md)
