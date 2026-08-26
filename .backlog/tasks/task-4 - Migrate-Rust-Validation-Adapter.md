---
id: TASK-4
title: Migrate Rust Validation Adapter
status: Done
assignee:
  - '@yewfence'
created_date: '2026-08-25 10:10'
updated_date: '2026-08-26 16:57'
labels:
  - execution-ready
milestone: m-0
dependencies:
  - TASK-2
documentation:
  - .backlog/docs/specifications/staging-validation-monorepo/doc-1
modified_files:
  - overlays/rust/mise.toml
  - overlays/rust/validation/__init__.py
  - overlays/rust/validation/check.py
  - tools/template-tool/src/template_tool/staging_validation/runtime.py
  - tools/template-tool/tests/test_validation_adapters.py
type: enhancement
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Outcome

让 Rust validation 使用 shared runtime，并保留 Rust 自己的 identity、docs-site、codecov-upload 和 crates-io-publish 合同及命令顺序。

## Source

- Backlog document: `doc-1`
- Canonical path: `.backlog/docs/specifications/staging-validation-monorepo/doc-1 - Staging-Validation-Monorepo-Refactor.md`
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 overlays/rust/mise.toml 不再包含长 validation shell。
- [x] #2 Rust adapter 不再枚举 capability Cartesian product。
- [x] #3 docs-site 的 enabled/disabled 输出、任务和工具合同保持现有行为。
- [x] #4 codecov-upload 的 Rust coverage tool、workflow、权限和 report 合同保持现有行为。
- [x] #5 crates-io-publish 的任务、jq 工具、可执行发布脚本、CI package check 和 release publish 合同保持现有行为。
- [x] #6 禁用 crates-io-publish 时，相关任务、工具、脚本和 workflow 行为仍完整缺席。
- [x] #7 Rust adapter 可以通过 //overlays/rust:check 调用。
- [x] #8 Rust profile-specific adapter tests 覆盖 crates.io capability 的启用和禁用路径。
- [x] #9 根 check-templates rust 仍能把每个 capability case 传给该 adapter。
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add Rust adapter seam tests and namespaced task discoverability coverage, replacing TOML shell extraction for Rust.
2. Implement overlays/rust/validation/check.py with shared docs-site and Codecov contracts plus Rust identity, crates.io, bootstrap, and final-check ordering.
3. Reduce overlays/rust/mise.toml to task registration and run focused adapter tests, full template-tool tests, and sync/topology checks.
4. Review the diff against doc-1 and record objective verification before finalizing the ticket.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Migrated Rust staging validation to the shared Python runtime while preserving identity, docs-site, Codecov, crates.io, bootstrap, and final check ordering. Rust adapter tests now call the Python interface directly and cover enabled/disabled crates.io paths plus namespaced task discovery.
Verification: focused adapter tests 22 passed; full template-tool suite 119 passed; mise task discovery/info/graph passed; sync:check reports repository/common/go-cli/rust in sync; git diff --check passed; no templates/ files changed. Root mise run check rust expanded and invoked all eight capability cases. With the host RUSTC_WRAPPER cleared, all four Codecov-disabled cases completed; the four Codecov-enabled cases reached the staged template final check and exposed a pre-existing nllint failure caused by whitespace in the non-default .github/workflows/coverage.yml output. This task does not modify that template source.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Migrated Rust staging validation from a 237-line inline shell to an overlay-owned Python adapter using the shared runtime. Preserved Rust identity, docs-site, Codecov, crates.io publishing, and command-order contracts; replaced TOML shell extraction with direct adapter tests and added Rust namespaced task coverage. Verified with 119 pytest tests, mise topology checks, sync:check, diff checks, and all eight root capability cases reaching the adapter.
<!-- SECTION:FINAL_SUMMARY:END -->
