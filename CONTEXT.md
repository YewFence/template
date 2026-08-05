# Template System

This repository maintains project blueprints and the infrastructure used to render and validate them.

## Language

**Template deliverable**:
The files delivered to a user as a starting point for a new project. It may declare fuzzy major versions and excludes generated dependency state.
_Avoid_: Reproducible template, locked template

**Maintenance environment**:
The monorepo-owned tools and CI used to render and validate template deliverables. Its dependency state and GitHub Actions remain precisely locked.
_Avoid_: Template environment

**Unbootstrapped template**:
A freshly rendered or applied template deliverable whose dependency state and GitHub Action digests have not been generated. It is not expected to pass the project checks.
_Avoid_: Broken template, incomplete render

**Bootstrapped project**:
A project whose native dependency state and GitHub Action digests have been generated from the template's fuzzy declarations and are ready to be version-controlled. Project checks are expected to pass from this state onward.
_Avoid_: Rendered template, locked template

**Compatibility line**:
The broadest version selector that an ecosystem treats as a meaningful compatibility boundary. It is usually a stable major line, but may be a pre-1.0 minor line or a concrete version where the ecosystem does not support ranges.
_Avoid_: Fuzzy major, latest version, exact pin

**Project instantiation**:
The one-time transformation from a generic template blueprint into a project-specific tree, including project identity tokens and language-specific names or module paths. It belongs to the external template tool rather than the delivered project's mise tasks; `init-project` performs it for new repositories, while `apply-template` does not rewrite an existing project's identity.
_Avoid_: Template init task, project bootstrap, dependency bootstrap

**Validation adapter**:
A monorepo-only mise task under a template overlay that generates disposable dependency state and then runs the staged template's own checks. It is not part of the template deliverable.
_Avoid_: Lock updater, template check
