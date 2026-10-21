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

The `#subdirectory=tools/template-tool` fragment is mandatory: the repository root is not a Python project, so a `--from` without it fails to resolve. `--ref main` tracks the newest contract; a release tag freezes it. Pass the same `--ref` to every command in one run, and pass it to the user when reporting what was run.

Three decisions precede the run. The **profile** is yours to determine from the user's request and the target's shape, with the user asked only when the evidence is genuinely ambiguous. The **capability set** belongs to the user: show every declared capability and let silence mean the default. **Metadata** is the user's to state and never yours to guess. Settle all three before running anything, because a template run is not repeatable — there is no template-upgrade contract.

## 1. Discover the profiles this ref declares

Never work from a remembered profile list, and never carry one over from another ref. Ask the selected ref what it declares:

```bash
$TPL list-templates --ref main
$TPL list-templates --ref main --json
```

The text form prints, per profile, its declared capabilities with default state and its required metadata fields. The `--json` form is the same contract as one stable object for scripting. Read the whole list before choosing — the set of profiles changes as templates are added.

**Done when** you have the ref's profile list in hand, including each profile's capabilities and required metadata fields.

## 2. Decide the profile

Match the target's shape against the profiles you just read. Read the target repository before asking anything: existing language sources, module files, build manifests, and the git remote usually settle it — a `pyproject.toml`-based Python project is the Python profile, a Go module with a Cobra command tree is the Go CLI profile, a `Cargo.toml` is the Rust profile, a `package.json` with a TypeScript src layout is the Node profile. Pick the language-agnostic profile when the repository brings its own language tasks or uses a language none of the declared profiles own.

Ask only when the evidence leaves two profiles plausible, and ask with your reading attached — "this looks like a Rust CLI, so the Rust profile; confirm?" beats an open question.

**Done when** you can name one declared profile and the concrete evidence for it.

## 3. Collect the capability set

Show every capability the chosen profile declares, with its default state and what it adds. This is the decision the user always takes part in. The selected ref's contract is the only source of truth for this list — never carry a capability set from memory, from another ref, or from an earlier run. An explicit answer wins; silence means the default. Resolve the whole set before running.

```bash
$TPL list-template-capabilities --ref main --template <profile> --json
```

Use this per-profile form when you want the capability contract alone; the profile list from step 1 already carries the same information.

**Done when** every declared capability is either answered explicitly or covered by the user's "defaults are fine", and you have stated the resulting enable/disable overrides.

## 4. Collect metadata

Every required field comes from the user. The tool refuses to guess, for good reason: identity lands in the initial commit, module paths, and workflow files. Take the required field list for the chosen profile from step 1 — do not assume it. You may propose candidates derived from the repository — directory name, git remote, existing module path — but each one is confirmed before use. When the user answers "you decide" for a field, propose one concrete value and wait for confirmation rather than filling it in silently.

**Done when** every field the profile requires has a value the user confirmed, with none inferred.

## 5. Run the entry point that matches the target

Two entry points, two lifecycles. The target's state decides which one applies, and you say out loud which one you are running:

- **New repository** — `init-project`. Target must be the repository root and a clean Git repository with no commits. It creates the initial commit with your normal Git identity, then stages the instantiated project.
- **Existing repository** — `apply-template`. Target must be a clean Git repository with at least one commit, and must not be mid-merge, rebase, cherry-pick, or revert. It stages changes to the index and never commits.

```bash
$TPL init-project --ref main --template <profile> \
  [--enable-capability <name>]... [--disable-capability <name>]... \
  [<profile metadata fields as options>] .

$TPL apply-template --ref main --template <profile> \
  [--enable-capability <name>]... [--disable-capability <name>]... \
  [<profile metadata fields as options>] .
```

Each metadata field has a matching option: the field name with underscores turned into dashes, prefixed with `--` (`github_owner` → `--github-owner`), so the required field list from step 1 tells you the exact option names. `--interactive` collects the capability set and metadata as prompts instead.

The preconditions are hard: a repository with commits cannot be initialized, and a repository without commits cannot receive an application. When the target satisfies neither, stop and hand the state back to the user instead of bending the target with destructive Git commands or switching entry points to make it fit.

**Done when** the command exits 0 and `git status` and `git diff --cached` show the staged project.

## 6. Resolve what the tool left alone

Applying skips the root paths that carry project identity — `.gitignore`, `AGENTS*`, `LICENSE*`, `NOTICE*` — and leaves every conflicting path with its index stages and worktree state intact. Both sets are yours to finish.

For each conflicting or skipped path, understand the **intent** on both sides before writing anything: the project's existing meaning and the template's new automation. Keep both whenever they are independent; when the intents are genuinely incompatible, ask the user which one wins. Every resolution either preserves both intents or follows a decision the user made.

**Done when** no path keeps unresolved conflict content, and every path left untouched is reported to the user.

## 7. Bootstrap and verify

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

Review the generated `mise.lock`, `mise.ci.lock`, language dependency state, the docs lockfile, and pinact's workflow edits together with the project sources; they belong in the same commit. A green `mise run check` is what makes the project a bootstrapped project.

**Done when** `mise run check` passes, or you hand over the exact failing command and its output as an open problem rather than a finished run.

## 8. Hand over

The tool creates no remote and commits nothing on the user's behalf. Close by naming the project state, the profile you chose and the evidence behind it, the effective capability set, the ref that was used, and what still belongs to the user: the remote, the first push, capability secrets such as the Codecov token, and the release tag that triggers publishing.

**Done when** one summary leaves the user knowing both what exists and what remains.

## References

- Copying a few files from a newer ref, or upgrading by hand: [references/template-export.md](references/template-export.md)
- Command and option details, and the per-capability guides: <https://github.com/YewFence/template/tree/main/docs>
