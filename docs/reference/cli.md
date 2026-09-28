# CLI Reference

<!-- GENERATED FILE: do not edit by hand. Regenerate with `mise run docs:reference`. -->

This reference is generated from the tool's own `--help` output. Run any entry point with `--help` to see the same text interactively.

The user-facing commands are usually run through `uvx`, which fetches the selected ref of the template monorepo and executes its locked tool version:

```text
uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" <command> ...
```

## User Commands

### `init-project`

```text
usage: init-project [-h] [--repo REPO] --ref REF --template TEMPLATE
                    [--project-name PROJECT_NAME] [--description DESCRIPTION]
                    [--github-owner GITHUB_OWNER] [--repo-name REPO_NAME]
                    [--python-package PYTHON_PACKAGE] [--go-module GO_MODULE]
                    [--cargo-package CARGO_PACKAGE]
                    [--binary-name BINARY_NAME]
                    [--enable-capability ENABLE_CAPABILITY]
                    [--disable-capability DISABLE_CAPABILITY] [--interactive]
                    [--keep-tokens]
                    [target]

Initialize a new project from a template at the selected ref of the template
monorepo. The target must be a clean Git repository without any commits, and
the target path must be the repository root.

The tool validates the template contract, renders, and instantiates the
template in an isolated tree, creates the initial commit with your normal Git
identity (signing and hooks included), then stages the instantiated project as
uncommitted changes. It never guesses metadata, creates remotes, or commits
the template content for you.

positional arguments:
  target                clean Git repository without commits to initialize;
                        must be the repository root (default: current
                        directory)

options:
  -h, --help            show this help message and exit
  --repo REPO           template monorepo to fetch from (default:
                        https://github.com/YewFence/template.git)
  --ref REF             Git ref of the template monorepo to select, e.g. main
                        or a release tag; the template contract and renderer
                        always come from this ref
  --template TEMPLATE   template profile declared in templates.toml (e.g.
                        common, python, go-cli, rust)
  --project-name PROJECT_NAME
                        project display name (metadata field: project_name)
  --description DESCRIPTION
                        one-line project description (metadata field:
                        description)
  --github-owner GITHUB_OWNER
                        GitHub user or organization that will own the
                        repository (metadata field: github_owner)
  --repo-name REPO_NAME
                        GitHub repository name (metadata field: repo_name)
  --python-package PYTHON_PACKAGE
                        importable package identifier; python template only
                        (metadata field: python_package)
  --go-module GO_MODULE
                        Go module path; go-cli template only (metadata field:
                        go_module)
  --cargo-package CARGO_PACKAGE
                        Cargo package name; rust template only (metadata
                        field: cargo_package)
  --binary-name BINARY_NAME
                        name of the compiled binary; go-cli and rust templates
                        only (metadata field: binary_name)
  --enable-capability ENABLE_CAPABILITY
                        enable a template capability, overriding the profile
                        default; repeatable
  --disable-capability DISABLE_CAPABILITY
                        disable a template capability, overriding the profile
                        default; repeatable
  --interactive         choose capabilities and answer metadata fields
                        interactively, with a summary confirmation before
                        anything is changed
  --keep-tokens         stage the raw template blueprint without replacing
                        {{METADATA}} tokens; cannot be combined with metadata
                        options

examples:
  uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" init-project --ref main --template common --interactive .

Use --interactive to pick capabilities and answer metadata fields, or pass
--enable-capability/--disable-capability and metadata options for scripted
use. After instantiation, generate and commit the project's own dependency
lock state and GitHub Action digests as described in the README.
```

### `apply-template`

```text
usage: apply-template [-h] [--repo REPO] --ref REF --template TEMPLATE
                      [--project-name PROJECT_NAME]
                      [--description DESCRIPTION]
                      [--github-owner GITHUB_OWNER] [--repo-name REPO_NAME]
                      [--python-package PYTHON_PACKAGE]
                      [--go-module GO_MODULE] [--cargo-package CARGO_PACKAGE]
                      [--binary-name BINARY_NAME]
                      [--enable-capability ENABLE_CAPABILITY]
                      [--disable-capability DISABLE_CAPABILITY]
                      [--interactive] [--keep-tokens]
                      [target]

Apply a template at the selected ref to an existing repository. The target
must be a clean Git repository with at least one commit, and must not be in
the middle of a merge, rebase, cherry-pick, or revert.

Template changes are staged to the Git index only; nothing is committed
automatically. Root .gitignore, AGENTS*, license, and notice files are
protected and skipped. Conflicting paths keep their Git index stages and
worktree state for manual resolution.

positional arguments:
  target                existing clean Git repository to receive the template
                        (default: current directory)

options:
  -h, --help            show this help message and exit
  --repo REPO           template monorepo to fetch from (default:
                        https://github.com/YewFence/template.git)
  --ref REF             Git ref of the template monorepo to select, e.g. main
                        or a release tag; the template contract and renderer
                        always come from this ref
  --template TEMPLATE   template profile declared in templates.toml (e.g.
                        common, python, go-cli, rust)
  --project-name PROJECT_NAME
                        project display name (metadata field: project_name)
  --description DESCRIPTION
                        one-line project description (metadata field:
                        description)
  --github-owner GITHUB_OWNER
                        GitHub user or organization that will own the
                        repository (metadata field: github_owner)
  --repo-name REPO_NAME
                        GitHub repository name (metadata field: repo_name)
  --python-package PYTHON_PACKAGE
                        importable package identifier; python template only
                        (metadata field: python_package)
  --go-module GO_MODULE
                        Go module path; go-cli template only (metadata field:
                        go_module)
  --cargo-package CARGO_PACKAGE
                        Cargo package name; rust template only (metadata
                        field: cargo_package)
  --binary-name BINARY_NAME
                        name of the compiled binary; go-cli and rust templates
                        only (metadata field: binary_name)
  --enable-capability ENABLE_CAPABILITY
                        enable a template capability, overriding the profile
                        default; repeatable
  --disable-capability DISABLE_CAPABILITY
                        disable a template capability, overriding the profile
                        default; repeatable
  --interactive         choose capabilities and answer metadata fields
                        interactively, with a summary confirmation before
                        anything is changed
  --keep-tokens         stage the raw template blueprint without replacing
                        {{METADATA}} tokens; cannot be combined with metadata
                        options

examples:
  uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" apply-template --ref main --template go-cli --interactive .

Review the staged changes with `git status` and `git diff --cached`, then
commit them yourself. Cancel the whole application with `git reset --hard
HEAD`. Detached HEAD and colocated Jujutsu repositories are supported, but
finish, resolve, or cancel this Git application before continuing normal jj
operations.
```

### `export-template`

```text
usage: export-template [-h] [--repo REPO] --ref REF --template TEMPLATE
                       [--project-name PROJECT_NAME]
                       [--description DESCRIPTION]
                       [--github-owner GITHUB_OWNER] [--repo-name REPO_NAME]
                       [--python-package PYTHON_PACKAGE]
                       [--go-module GO_MODULE] [--cargo-package CARGO_PACKAGE]
                       [--binary-name BINARY_NAME]
                       [--enable-capability ENABLE_CAPABILITY]
                       [--disable-capability DISABLE_CAPABILITY]
                       [--interactive]
                       destination

Export a template at the selected ref as a standalone candidate tree for
manual comparison and selective copying, for example to diff a newer template
ref against an existing project.

The destination must not exist or be empty. Metadata is preset to placeholder
values so non-interactive exports need no project identity. The export creates
no .git directory, applies no protected-path filtering, and never touches an
existing project.

positional arguments:
  destination           directory for the candidate tree; must not exist or be
                        empty

options:
  -h, --help            show this help message and exit
  --repo REPO           template monorepo to fetch from (default:
                        https://github.com/YewFence/template.git)
  --ref REF             Git ref of the template monorepo to select, e.g. main
                        or a release tag; the template contract and renderer
                        always come from this ref
  --template TEMPLATE   template profile declared in templates.toml (e.g.
                        common, python, go-cli, rust)
  --project-name PROJECT_NAME
                        project display name (metadata field: project_name)
  --description DESCRIPTION
                        one-line project description (metadata field:
                        description)
  --github-owner GITHUB_OWNER
                        GitHub user or organization that will own the
                        repository (metadata field: github_owner)
  --repo-name REPO_NAME
                        GitHub repository name (metadata field: repo_name)
  --python-package PYTHON_PACKAGE
                        importable package identifier; python template only
                        (metadata field: python_package)
  --go-module GO_MODULE
                        Go module path; go-cli template only (metadata field:
                        go_module)
  --cargo-package CARGO_PACKAGE
                        Cargo package name; rust template only (metadata
                        field: cargo_package)
  --binary-name BINARY_NAME
                        name of the compiled binary; go-cli and rust templates
                        only (metadata field: binary_name)
  --enable-capability ENABLE_CAPABILITY
                        enable a template capability, overriding the profile
                        default; repeatable
  --disable-capability DISABLE_CAPABILITY
                        disable a template capability, overriding the profile
                        default; repeatable
  --interactive         choose capabilities and answer metadata fields
                        interactively, with a summary confirmation before
                        anything is changed

examples:
  uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" export-template --ref main --template rust --interactive ./rust-template-main

The exported tree is an unbootstrapped template blueprint: dependency lock
state and GitHub Action digests are not generated.
```

### `list-template-capabilities`

```text
usage: list-template-capabilities [-h] [--repo REPO] --ref REF
                                  --template TEMPLATE [--json]

Print the capabilities a template declares at the selected ref, together with
their default state. Read-only: the command only reads the capability contract
of the selected ref. It requires no Git repository and changes nothing.

options:
  -h, --help           show this help message and exit
  --repo REPO          template monorepo to fetch from (default:
                       https://github.com/YewFence/template.git)
  --ref REF            Git ref of the template monorepo to select, e.g. main
                       or a release tag; the template contract and renderer
                       always come from this ref
  --template TEMPLATE  template profile declared in templates.toml (e.g.
                       common, python, go-cli, rust)
  --json               print the capability contract as a stable single-line
                       JSON object for scripting

examples:
  uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" list-template-capabilities --ref main --template rust
  uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" list-template-capabilities --ref main --template rust --json
```

## Maintenance Commands

### `render-template`

```text
usage: render-template [-h] [--check] [--root ROOT] [template]

Render template previews from the shared/ and overlays/ sources into
templates/<name>/ in the local monorepo checkout. Maintenance command; users
of the templates do not need it.

positional arguments:
  template     template name; defaults to all

options:
  -h, --help   show this help message and exit
  --check      compare generated output without writing
  --root ROOT  monorepo root containing templates.toml (default: current
               directory)
```

### `check-templates`

```text
usage: check-templates [-h] [--root ROOT] [template]

Check that the committed template previews are in sync with their sources,
then validate every capability combination of each selected template in
disposable staging. Maintenance command; normally run by monorepo CI.

positional arguments:
  template     template name; defaults to all

options:
  -h, --help   show this help message and exit
  --root ROOT  monorepo root containing templates.toml (default: current
               directory)
```

### `template-tool`

```text
usage: template-tool [-h] {render,check,apply,init,export,capabilities} ...

Unified entry point for all template tool commands. The user-facing commands
are also available as standalone entry points (init-project, apply-template,
export-template, list-template-capabilities) that bootstrap into the selected
ref's own locked tool version before running.

positional arguments:
  {render,check,apply,init,export,capabilities}
    render              render template previews from sources
    check               validate templates in disposable staging
    apply               apply a template to an existing repository
    init                initialize a new project from a template
    export              export a standalone candidate tree
    capabilities        list a template's declared capabilities

options:
  -h, --help            show this help message and exit
```

#### `template-tool render`

```text
usage: template-tool render [-h] [--check] [--root ROOT] [template]

Render template previews from the shared/ and overlays/ sources into
templates/<name>/ in the local monorepo checkout. Maintenance command; users
of the templates do not need it.

positional arguments:
  template     template name; defaults to all

options:
  -h, --help   show this help message and exit
  --check      compare generated output without writing
  --root ROOT  monorepo root containing templates.toml (default: current
               directory)
```

#### `template-tool check`

```text
usage: template-tool check [-h] [--root ROOT] [template]

Check that the committed template previews are in sync with their sources,
then validate every capability combination of each selected template in
disposable staging. Maintenance command; normally run by monorepo CI.

positional arguments:
  template     template name; defaults to all

options:
  -h, --help   show this help message and exit
  --root ROOT  monorepo root containing templates.toml (default: current
               directory)
```

#### `template-tool apply`

```text
usage: template-tool apply [-h] [--repo REPO] --ref REF --template TEMPLATE
                           [--project-name PROJECT_NAME]
                           [--description DESCRIPTION]
                           [--github-owner GITHUB_OWNER]
                           [--repo-name REPO_NAME]
                           [--python-package PYTHON_PACKAGE]
                           [--go-module GO_MODULE]
                           [--cargo-package CARGO_PACKAGE]
                           [--binary-name BINARY_NAME]
                           [--enable-capability ENABLE_CAPABILITY]
                           [--disable-capability DISABLE_CAPABILITY]
                           [--interactive] [--keep-tokens]
                           [target]

Apply a template at the selected ref to an existing repository. The target
must be a clean Git repository with at least one commit, and must not be in
the middle of a merge, rebase, cherry-pick, or revert.

Template changes are staged to the Git index only; nothing is committed
automatically. Root .gitignore, AGENTS*, license, and notice files are
protected and skipped. Conflicting paths keep their Git index stages and
worktree state for manual resolution.

positional arguments:
  target                existing clean Git repository to receive the template
                        (default: current directory)

options:
  -h, --help            show this help message and exit
  --repo REPO           template monorepo to fetch from (default:
                        https://github.com/YewFence/template.git)
  --ref REF             Git ref of the template monorepo to select, e.g. main
                        or a release tag; the template contract and renderer
                        always come from this ref
  --template TEMPLATE   template profile declared in templates.toml (e.g.
                        common, python, go-cli, rust)
  --project-name PROJECT_NAME
                        project display name (metadata field: project_name)
  --description DESCRIPTION
                        one-line project description (metadata field:
                        description)
  --github-owner GITHUB_OWNER
                        GitHub user or organization that will own the
                        repository (metadata field: github_owner)
  --repo-name REPO_NAME
                        GitHub repository name (metadata field: repo_name)
  --python-package PYTHON_PACKAGE
                        importable package identifier; python template only
                        (metadata field: python_package)
  --go-module GO_MODULE
                        Go module path; go-cli template only (metadata field:
                        go_module)
  --cargo-package CARGO_PACKAGE
                        Cargo package name; rust template only (metadata
                        field: cargo_package)
  --binary-name BINARY_NAME
                        name of the compiled binary; go-cli and rust templates
                        only (metadata field: binary_name)
  --enable-capability ENABLE_CAPABILITY
                        enable a template capability, overriding the profile
                        default; repeatable
  --disable-capability DISABLE_CAPABILITY
                        disable a template capability, overriding the profile
                        default; repeatable
  --interactive         choose capabilities and answer metadata fields
                        interactively, with a summary confirmation before
                        anything is changed
  --keep-tokens         stage the raw template blueprint without replacing
                        {{METADATA}} tokens; cannot be combined with metadata
                        options

examples:
  uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" apply-template --ref main --template go-cli --interactive .

Review the staged changes with `git status` and `git diff --cached`, then
commit them yourself. Cancel the whole application with `git reset --hard
HEAD`. Detached HEAD and colocated Jujutsu repositories are supported, but
finish, resolve, or cancel this Git application before continuing normal jj
operations.
```

#### `template-tool init`

```text
usage: template-tool init [-h] [--repo REPO] --ref REF --template TEMPLATE
                          [--project-name PROJECT_NAME]
                          [--description DESCRIPTION]
                          [--github-owner GITHUB_OWNER]
                          [--repo-name REPO_NAME]
                          [--python-package PYTHON_PACKAGE]
                          [--go-module GO_MODULE]
                          [--cargo-package CARGO_PACKAGE]
                          [--binary-name BINARY_NAME]
                          [--enable-capability ENABLE_CAPABILITY]
                          [--disable-capability DISABLE_CAPABILITY]
                          [--interactive] [--keep-tokens]
                          [target]

Initialize a new project from a template at the selected ref of the template
monorepo. The target must be a clean Git repository without any commits, and
the target path must be the repository root.

The tool validates the template contract, renders, and instantiates the
template in an isolated tree, creates the initial commit with your normal Git
identity (signing and hooks included), then stages the instantiated project as
uncommitted changes. It never guesses metadata, creates remotes, or commits
the template content for you.

positional arguments:
  target                clean Git repository without commits to initialize;
                        must be the repository root (default: current
                        directory)

options:
  -h, --help            show this help message and exit
  --repo REPO           template monorepo to fetch from (default:
                        https://github.com/YewFence/template.git)
  --ref REF             Git ref of the template monorepo to select, e.g. main
                        or a release tag; the template contract and renderer
                        always come from this ref
  --template TEMPLATE   template profile declared in templates.toml (e.g.
                        common, python, go-cli, rust)
  --project-name PROJECT_NAME
                        project display name (metadata field: project_name)
  --description DESCRIPTION
                        one-line project description (metadata field:
                        description)
  --github-owner GITHUB_OWNER
                        GitHub user or organization that will own the
                        repository (metadata field: github_owner)
  --repo-name REPO_NAME
                        GitHub repository name (metadata field: repo_name)
  --python-package PYTHON_PACKAGE
                        importable package identifier; python template only
                        (metadata field: python_package)
  --go-module GO_MODULE
                        Go module path; go-cli template only (metadata field:
                        go_module)
  --cargo-package CARGO_PACKAGE
                        Cargo package name; rust template only (metadata
                        field: cargo_package)
  --binary-name BINARY_NAME
                        name of the compiled binary; go-cli and rust templates
                        only (metadata field: binary_name)
  --enable-capability ENABLE_CAPABILITY
                        enable a template capability, overriding the profile
                        default; repeatable
  --disable-capability DISABLE_CAPABILITY
                        disable a template capability, overriding the profile
                        default; repeatable
  --interactive         choose capabilities and answer metadata fields
                        interactively, with a summary confirmation before
                        anything is changed
  --keep-tokens         stage the raw template blueprint without replacing
                        {{METADATA}} tokens; cannot be combined with metadata
                        options

examples:
  uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" init-project --ref main --template common --interactive .

Use --interactive to pick capabilities and answer metadata fields, or pass
--enable-capability/--disable-capability and metadata options for scripted
use. After instantiation, generate and commit the project's own dependency
lock state and GitHub Action digests as described in the README.
```

#### `template-tool export`

```text
usage: template-tool export [-h] [--repo REPO] --ref REF --template TEMPLATE
                            [--project-name PROJECT_NAME]
                            [--description DESCRIPTION]
                            [--github-owner GITHUB_OWNER]
                            [--repo-name REPO_NAME]
                            [--python-package PYTHON_PACKAGE]
                            [--go-module GO_MODULE]
                            [--cargo-package CARGO_PACKAGE]
                            [--binary-name BINARY_NAME]
                            [--enable-capability ENABLE_CAPABILITY]
                            [--disable-capability DISABLE_CAPABILITY]
                            [--interactive]
                            destination

Export a template at the selected ref as a standalone candidate tree for
manual comparison and selective copying, for example to diff a newer template
ref against an existing project.

The destination must not exist or be empty. Metadata is preset to placeholder
values so non-interactive exports need no project identity. The export creates
no .git directory, applies no protected-path filtering, and never touches an
existing project.

positional arguments:
  destination           directory for the candidate tree; must not exist or be
                        empty

options:
  -h, --help            show this help message and exit
  --repo REPO           template monorepo to fetch from (default:
                        https://github.com/YewFence/template.git)
  --ref REF             Git ref of the template monorepo to select, e.g. main
                        or a release tag; the template contract and renderer
                        always come from this ref
  --template TEMPLATE   template profile declared in templates.toml (e.g.
                        common, python, go-cli, rust)
  --project-name PROJECT_NAME
                        project display name (metadata field: project_name)
  --description DESCRIPTION
                        one-line project description (metadata field:
                        description)
  --github-owner GITHUB_OWNER
                        GitHub user or organization that will own the
                        repository (metadata field: github_owner)
  --repo-name REPO_NAME
                        GitHub repository name (metadata field: repo_name)
  --python-package PYTHON_PACKAGE
                        importable package identifier; python template only
                        (metadata field: python_package)
  --go-module GO_MODULE
                        Go module path; go-cli template only (metadata field:
                        go_module)
  --cargo-package CARGO_PACKAGE
                        Cargo package name; rust template only (metadata
                        field: cargo_package)
  --binary-name BINARY_NAME
                        name of the compiled binary; go-cli and rust templates
                        only (metadata field: binary_name)
  --enable-capability ENABLE_CAPABILITY
                        enable a template capability, overriding the profile
                        default; repeatable
  --disable-capability DISABLE_CAPABILITY
                        disable a template capability, overriding the profile
                        default; repeatable
  --interactive         choose capabilities and answer metadata fields
                        interactively, with a summary confirmation before
                        anything is changed

examples:
  uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" export-template --ref main --template rust --interactive ./rust-template-main

The exported tree is an unbootstrapped template blueprint: dependency lock
state and GitHub Action digests are not generated.
```

#### `template-tool capabilities`

```text
usage: template-tool capabilities [-h] [--repo REPO] --ref REF
                                  --template TEMPLATE [--json]

Print the capabilities a template declares at the selected ref, together with
their default state. Read-only: the command only reads the capability contract
of the selected ref. It requires no Git repository and changes nothing.

options:
  -h, --help           show this help message and exit
  --repo REPO          template monorepo to fetch from (default:
                       https://github.com/YewFence/template.git)
  --ref REF            Git ref of the template monorepo to select, e.g. main
                       or a release tag; the template contract and renderer
                       always come from this ref
  --template TEMPLATE  template profile declared in templates.toml (e.g.
                       common, python, go-cli, rust)
  --json               print the capability contract as a stable single-line
                       JSON object for scripting

examples:
  uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" list-template-capabilities --ref main --template rust
  uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" list-template-capabilities --ref main --template rust --json
```
