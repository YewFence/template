---
name: use-template
description: "User-invoked only. Invoke this Skill only when the user explicitly requests the `use-template` Skill by name. Instantiates a YewFence project template into a new or existing repository, then bootstraps it to a passing check."
disable-model-invocation: true
---

# Use a Project Template

The templates live in the `YewFence/template` monorepo and are consumed through `uvx`. The selected ref supplies both the template contract and the renderer, so this Skill needs no local checkout of that monorepo. The result is self-contained: a generated project never depends on the template monorepo at runtime.

Set the launcher once and reuse it for every command below:

```bash
TPL='uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool"'
```

`--ref main` tracks the newest contract; a release tag freezes it. Pass the same `--ref` to every command in one run, and pass it to the user when reporting what was run.

Three decisions precede the run. The **profile** is yours to determine from the user's request and the target's shape — a Rust project gets `rust`, never `common` — with the user asked only when the evidence is genuinely ambiguous. The **capability set** belongs to the user: show every declared capability and let silence mean the default. **Metadata** is the user's to state and never yours to guess. Settle all three before running anything, because a template run is not repeatable — there is no template-upgrade contract.

## 1. Decide the profile

| Profile | Shape signal | Extra metadata |
| --- | --- | --- |
| `common` | Language-agnostic repository automation; the user brings their own language tasks, which ship as `[PLACEHOLDER]` stubs | — |
| `go-cli` | Go CLI with a Cobra skeleton and multi-platform release builds | `go_module`, `binary_name` |
| `rust` | Rust CLI with a locked-by-default Cargo workflow | `cargo_package`, `binary_name` |

Read the target repository before asking anything. Existing language sources, module files, build manifests, and the git remote usually settle it: a Go module with a Cobra command tree is `go-cli`, a `Cargo.toml` is `rust`, a repository whose language tooling the templates do not own is `common`.

Ask only when the evidence leaves two profiles plausible, and ask with your reading attached — "this looks like a Rust CLI, so `rust`; confirm?" beats an open question. A project that brings its own language tasks, which ship as `[PLACEHOLDER]` stubs, or uses a language none of these cover, is `common`.

**Done when** you can name one profile and the concrete evidence for it.

## 2. Collect the capability set

Read what the selected ref actually declares, then show all of it to the user:

```bash
$TPL list-template-capabilities --ref main --template <profile> --json
```

Present every declared capability with its default state and what it adds. This is the decision the user always takes part in. The selected ref's contract is the only source of truth for this list — never carry a capability set from memory, from another ref, or from an earlier run. An explicit answer wins; silence means the default. Resolve the whole set before running.

**Done when** every declared capability is either answered explicitly or covered by the user's "defaults are fine", and you have stated the resulting enable/disable overrides.

## 3. Collect metadata

Every required field comes from the user. The tool refuses to guess, for good reason: identity lands in the initial commit, module paths, and workflow files. You may propose candidates derived from the repository — directory name, git remote, existing module path — but each one is confirmed before use.

`project_name`, `description`, `github_owner`, and `repo_name` are required by every profile; the extra fields are in the profile table. When the user answers "you decide" for a field, propose one concrete value and wait for confirmation rather than filling it in silently.

**Done when** every field the profile requires has a value the user confirmed, with none inferred.

## 4. Run the entry point that matches the target

Two entry points, two lifecycles. The target's state decides which one applies, and you say out loud which one you are running:

- **New repository** — `init-project`. Target must be the repository root and a clean Git repository with no commits. It creates the initial commit with your normal Git identity, then stages the instantiated project.
- **Existing repository** — `apply-template`. Target must be a clean Git repository with at least one commit, and must not be mid-merge, rebase, cherry-pick, or revert. It stages changes to the index and never commits.

```bash
$TPL init-project --ref main --template <profile> \
  [--enable-capability <name>]... [--disable-capability <name>]... \
  --project-name "..." --description "..." \
  --github-owner ... --repo-name ... \
  [<profile extra fields>] .

$TPL apply-template --ref main --template <profile> \
  [--enable-capability <name>]... [--disable-capability <name>]... \
  --project-name "..." --description "..." \
  --github-owner ... --repo-name ... \
  [<profile extra fields>] .
```

The preconditions are hard: a repository with commits cannot be initialized, and a repository without commits cannot receive an application. When the target satisfies neither, stop and hand the state back to the user instead of bending the target with destructive Git commands or switching entry points to make it fit.

**Done when** the command exits 0 and `git status` and `git diff --cached` show the staged project.

## 5. Resolve what the tool left alone

Applying skips the root paths that carry project identity — `.gitignore`, `AGENTS*`, `LICENSE*`, `NOTICE*` — and leaves every conflicting path with its index stages and worktree state intact. Both sets are yours to finish.

For each conflicting or skipped path, understand the **intent** on both sides before writing anything: the project's existing meaning and the template's new automation. Keep both whenever they are independent; when the intents are genuinely incompatible, ask the user which one wins. Every resolution either preserves both intents or follows a decision the user made.

**Done when** no path keeps unresolved conflict content, and every path left untouched is reported to the user.

## 6. Bootstrap and verify

Instantiation produces an unbootstrapped template. Generate the project's own dependency state and GitHub Action digests with the project's real commands:

```bash
mise trust
mise -E ci lock
mise install --locked
mise run deps:update
mise run docs:install   # only with the docs-site capability
mise run actions:update
mise run hooks:install
mise run check
```

Review the generated `mise.lock`, `mise.ci.lock`, language dependency state, `docs/pnpm-lock.yaml`, and pinact's workflow edits together with the project sources; they belong in the same commit. A green `mise run check` is what makes the project a bootstrapped project.

**Done when** `mise run check` passes, or you hand over the exact failing command and its output as an open problem rather than a finished run.

## 7. Hand over

The tool creates no remote and commits nothing on the user's behalf. Close by naming the project state, the profile you chose and the evidence behind it, the effective capability set, the ref that was used, and what still belongs to the user: the remote, the first push, capability secrets such as the Codecov token, and the release tag that triggers publishing.

**Done when** one summary leaves the user knowing both what exists and what remains.

## References

- Copying a few files from a newer ref, or upgrading by hand: [references/template-export.md](references/template-export.md)
- Command and option details, and the per-capability guides: <https://github.com/YewFence/template/tree/main/docs>
