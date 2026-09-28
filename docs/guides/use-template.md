# Using the Templates

This guide covers every way to consume the templates in this monorepo. All commands run through `uvx`, which fetches the selected ref of the template monorepo and executes its locked tool version. For the full option list of each command see the [CLI reference](../reference/cli.md) — or just run any command with `--help`.

## Requirements

- Git
- [uv](https://docs.astral.sh/uv/) for `uvx`
- Generated projects expect [mise](https://mise.jdx.dev/) for toolchain and task management

## Create a New Project

Use `init-project`. The target must be a clean Git repository without any commits, and the target path must be the repository root.

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

With `--interactive`, the tool first asks which capabilities to enable, then asks for the required metadata fields (GitHub owner, repository name, description, and template-specific fields), and finally asks for one summary confirmation before it changes anything. It creates the initial commit with your normal Git identity — signing and hooks included — then stages the instantiated project as uncommitted changes.

After instantiation, generate and commit the project's own dependency lock state and GitHub Action digests with the real commands:

```bash
mise trust
mise -E ci lock
mise install --locked
mise run deps:update
mise run docs:install   # exists when the docs-site capability is enabled
mise run actions:update
mise run hooks:install
mise run check
```

Review the generated `mise.lock`, `mise.ci.lock`, Go/Cargo dependency state, `docs/pnpm-lock.yaml`, and pinact's workflow changes together with the project sources, then commit them. From this point on the project is a bootstrapped project and `mise run check` is expected to pass.

## Apply to an Existing Repository

Use `apply-template`. The target must be a clean Git repository with at least one commit, and must not be in the middle of a merge, rebase, cherry-pick, or revert.

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  apply-template \
  --ref main \
  --template go-cli \
  --interactive \
  .
```

On success the template changes land in the Git index only; the tool never commits for you. The interactive flow is the same as `init-project`.

Root-level `.gitignore`, `AGENTS*`, license, and notice files are protected and skipped — compare them with the template manually when needed. Other conflicts keep their Git index stages and worktree state for manual resolution: resolve the files, run `git add`, review with `git status` and `git diff --cached`, then commit yourself. To cancel the whole application, run `git reset --hard HEAD`.

Detached HEAD and colocated Jujutsu repositories are supported, but finish, resolve, or cancel this Git application before continuing normal `jj` operations.

Passing `--keep-tokens` stages the raw template blueprint without replacing `{{METADATA}}` tokens — useful when you want to instantiate by hand. It cannot be combined with metadata options.

## Export a Candidate Tree

There is no repeated-apply or template-upgrade contract. To upgrade, export the newest template ref into a temporary directory, diff it against your project, and copy over what you want.

`export-template` still asks for the capability set, but presets the required metadata fields to placeholder values — press Enter to skip through them. The destination must not exist or be empty, and no `.git` is created.

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  export-template \
  --ref main \
  --template rust \
  --interactive \
  ./rust-template-main
```

The exported tree is an unbootstrapped template blueprint: dependency lock state and GitHub Action digests are not generated.

## Query Template Capabilities

Before applying, read the capabilities a template declares at a selected ref, with their default state:

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  list-template-capabilities \
  --ref main \
  --template rust
```

Add `--json` for a stable, scriptable object. The command requires explicit `--ref` and `--template`, accepts no target path or capability overrides, and does not require the current directory to be a Git repository — it only reads the selected ref's capability contract.

## Non-Interactive Usage

Every interactive prompt has a scripted equivalent: pass capability choices with `--enable-capability`/`--disable-capability` (repeatable) and metadata fields as options such as `--github-owner` or `--repo-name`. For example:

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  init-project \
  --ref main \
  --template go-cli \
  --enable-capability container-image-publish \
  --project-name "My CLI" \
  --description "My CLI description" \
  --github-owner you \
  --repo-name your-cli \
  --go-module github.com/you/your-cli \
  --binary-name your-cli \
  .
```

## Bash Fallback

With the monorepo cloned locally, and only when uv is unavailable, try:

```bash
./scripts/apply-template --ref HEAD --repo /path/to/this/monorepo --template common /path/to/repository
```

The Bash launcher first fetches the selected ref shallowly for the whole repository. When uv is available on the system, it runs the applier inside the checkout's locked `tools/template-tool/uv.lock` environment. Without uv it is a best-effort fallback: it requires Git, Python, and the applier's Python dependencies to already exist on the system, creates no venv, resolves no uv lockfile, and does not guarantee that an old launcher stays compatible with arbitrary future template refs. Use the uvx paths above whenever dependencies are missing or you need strict version selection.

## Next Steps

- Per-template specifics: [common](../../overlays/common/README.md), [python](../../overlays/python/README.md), [go-cli](../../overlays/go-cli/README.md), [rust](../../overlays/rust/README.md)
- Projects with `codecov-upload` enabled: [Codecov upload guide](codecov-upload.md)
- Rust projects with `crates-io-publish` enabled: [crates.io publishing guide](rust-crates-io-publishing.md)
- Go CLI projects with `container-image-publish` enabled: [container image publishing guide](go-cli-container-image-publishing.md)
