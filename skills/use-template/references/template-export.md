# Export and Selective Copy

The main path in [SKILL.md](../SKILL.md) covers creating a project. Read this when the user explicitly wants only a few files from a template — an upgrade by hand, or a piece of automation lifted into an existing project.

There is no repeated-apply and no template-upgrade contract. The workflow is export, diff, copy selectively.

```bash
TPL='uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool"'

dest="$(mktemp -d)/template-export"
$TPL export-template --ref <ref> --template <profile> \
  [--enable-capability <name>]... [--disable-capability <name>]... \
  "$dest"

diff -ru --exclude=.git <project-root> "$dest"
```

The destination must not exist or be empty; `mktemp -d` gives you a safe parent. Export creates no `.git`, applies no protected-path filtering, and never touches an existing project.

## What the diff will contain

- **Identity placeholders.** Export presets metadata to placeholder values, so the tree reads `REPLACE ME: project name` and `replace-me-owner`. Identity differences against the project are expected noise, not changes to copy. Pass the metadata options instead when a real identity makes the diff easier to read.
- **Capability trees.** The capability set is selected per export. Pass the same enable/disable overrides the project was created with, or whole capability directories show up as additions you do not want.
- **Unbootstrapped state.** The export carries no dependency lock state and no pinned Action digests. Copying them over would clobber the project's bootstrapped state — leave them out.
- **Files the apply path would protect.** `.gitignore`, `AGENTS*`, `LICENSE*`, and `NOTICE*` appear here because export does not filter them. Compare them with the project by hand when the user wants them updated.

## Copy deliberately

Copy the paths the user asked for, one at a time, and keep the project's own intent in the surrounding files. Report the full list of copied paths, plus anything the diff showed that was left behind and why.

**Done when** the requested files are in place, no placeholder identity or lock state was copied, and the user knows which diffs you deliberately skipped.
