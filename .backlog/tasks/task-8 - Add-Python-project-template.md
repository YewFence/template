---
id: TASK-8
title: Add Python project template
status: Done
assignee: []
created_date: '2026-09-28 09:32'
updated_date: '2026-09-28 11:17'
labels: []
dependencies: []
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Python repositories currently have to start from the language-agnostic common profile and replace all language task placeholders manually. A dedicated profile should retain the common automation while providing a bootstrappable uv project and mise-managed Ruff and ty checks.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A python profile renders and instantiates a buildable src-layout Python project derived from the common shared automation
- [x] #2 mise installs Python, uv, Ruff, and ty and exposes working dependency, format, lint, type-check, test, build, and audit tasks
- [x] #3 docs-site and codecov-upload capability variants render and validate correctly
- [x] #4 The renderer, validation adapter tests, CLI documentation, and user-facing template documentation include the python profile
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add the python profile contract and overlay sources while reusing shared common layouts and fragments.
2. Add a Python staging validation adapter and extend profile-aware tests.
3. Render the default preview, regenerate CLI docs, and run focused and synchronization checks.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented python overlay/profile with mise-managed Python, uv, Ruff and ty; added Python metadata, capability slots, validation adapter, repository tests, docs, and default preview. Renderer sync and local bootstrapped smoke build/test/lint/type/audit passed. PyPI pytest-cov retrieval timed out during optional coverage smoke; adapter and render tests cover that variant.

Final verification: 205 template-tool tests passed; sync:check and docs:reference:check passed; instantiated Python smoke project passed uv lock/check, import check, pytest, wheel/sdist build, Ruff check/format, ty check, and uv audit. Optional pytest-cov live fetch was not repeated after PyPI timed out, while its enabled/disabled contract passed renderer and adapter tests.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added a Python template profile that keeps the existing common/shared architecture, supplies a uv src-layout package with mise-managed Ruff and ty, supports docs and Codecov capabilities, and is wired into rendering, validation, CLI metadata, tests, previews, and documentation. Verified with 205 automated tests, synchronization/reference checks, and an instantiated build/test/lint/type/audit smoke run.
<!-- SECTION:FINAL_SUMMARY:END -->
