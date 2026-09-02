---
id: TASK-6
title: Contract Old Validation Entrypoints and Update Documentation
status: Done
assignee:
  - '@yewfence'
created_date: '2026-08-25 10:19'
updated_date: '2026-09-02 09:51'
labels:
  - execution-ready
milestone: m-0
dependencies:
  - TASK-5
documentation:
  - .backlog/docs/specifications/staging-validation-monorepo/doc-1
type: enhancement
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Outcome

完成 expand-migrate-contract 的收缩阶段，删除已迁移的内联 shell 和旧测试辅助逻辑，并更新架构文档、术语和 namespaced task 使用说明。

## Source

- Backlog document: `doc-1`
- Canonical path: `.backlog/docs/specifications/staging-validation-monorepo/doc-1 - Staging-Validation-Monorepo-Refactor.md`
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 三个 overlays/*/mise.toml 仅保留 adapter task registration 和必要 metadata。
- [x] #2 旧 capability case 枚举、重复 shell helper 和 TOML extraction test helper 已删除。
- [x] #3 CONTEXT.md 中 Validation adapter 的定义与新 ownership 一致。
- [x] #4 docs/architecture/monorepo.md 准确说明 mise monorepo topology、template-tool 动态 staging ownership、overlay adapter ownership 和 namespaced task 调用方式。
- [x] #5 相关 plans 或维护文档不再声称 validation adapter 完全内联于 mise.toml。
- [x] #6 mise tasks ls --all、mise tasks graph、工具测试和 mise run sync:check 通过。
- [x] #7 默认 template snapshots 没有因 validation bootstrap 产生非预期差异。
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Audit overlays/*/mise.toml for leftover inline shell, capability case enumeration, and TOML extraction helpers; remove or confirm absence (AC#1, AC#2).
2. Update CONTEXT.md Validation adapter definition to the new ownership: overlay-owned Python check.py registered as a namespaced mise task (AC#3).
3. Update docs/architecture/monorepo.md: overlay directory tree, namespaced task wording, and staging step 4 to name the adapter invocation path accurately (AC#4).
4. Sweep plans, ADRs, and maintenance docs for stale claims of inline validation shell; update AGENTS.md directory responsibilities with overlays/<name>/validation/ (AC#5).
5. Verify: mise tasks ls --all, mise tasks graph, pytest, mise run sync:check, templates/ unchanged (AC#6, AC#7).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Contraction audit: all three overlays/*/mise.toml are 12 lines each with only task registration and the [env] _.path test hook from TASK-5; no inline shell, capability case enumeration, or Cartesian product remains. No tasks.check.run or /bin/bash -c references exist anywhere in tools/; TOML extraction test helpers were removed in TASK-5's test rewrite.
Docs: CONTEXT.md Validation adapter now defines the overlay-owned check.py entrypoint registered as a namespaced mise task. docs/architecture/monorepo.md directory tree includes overlays/<name>/validation/, namespaced task wording updated, and staging step 4 names the adapter registration path. AGENTS.md directory responsibilities now list overlays/<name>/validation/. plans/ and adr/ contain no stale inline-shell claims.
Verification: mise tasks ls --all shows all three overlay checks; mise tasks graph exit 0; pytest 152 passed; mise run sync:check reports repository/common/go-cli/rust in sync; git status shows no templates/ changes.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Completed the contract phase of the staging validation refactor: confirmed the three overlay mise.toml files carry only namespaced adapter registration plus the test-bin env hook, with all inline shell, capability case enumeration, and TOML extraction helpers gone. Updated CONTEXT.md's Validation adapter term, docs/architecture/monorepo.md (directory tree, topology wording, staging step 4), and AGENTS.md directory responsibilities; plans and ADRs carry no stale inline-shell claims. Verified with mise tasks ls --all, mise tasks graph (exit 0), 152 pytest tests, sync:check in sync for all templates, and no templates/ diffs.
<!-- SECTION:FINAL_SUMMARY:END -->
