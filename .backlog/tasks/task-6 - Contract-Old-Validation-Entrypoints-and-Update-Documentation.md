---
id: TASK-6
title: Contract Old Validation Entrypoints and Update Documentation
status: To Do
assignee: []
created_date: '2026-08-25 10:19'
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
- [ ] #1 三个 overlays/*/mise.toml 仅保留 adapter task registration 和必要 metadata。
- [ ] #2 旧 capability case 枚举、重复 shell helper 和 TOML extraction test helper 已删除。
- [ ] #3 CONTEXT.md 中 Validation adapter 的定义与新 ownership 一致。
- [ ] #4 docs/architecture/monorepo.md 准确说明 mise monorepo topology、template-tool 动态 staging ownership、overlay adapter ownership 和 namespaced task 调用方式。
- [ ] #5 相关 plans 或维护文档不再声称 validation adapter 完全内联于 mise.toml。
- [ ] #6 mise tasks ls --all、mise tasks graph、工具测试和 mise run sync:check 通过。
- [ ] #7 默认 template snapshots 没有因 validation bootstrap 产生非预期差异。
<!-- AC:END -->
