---
id: TASK-4
title: Migrate Rust Validation Adapter
status: To Do
assignee: []
created_date: '2026-08-25 10:10'
labels:
  - execution-ready
milestone: m-0
dependencies:
  - TASK-2
documentation:
  - .backlog/docs/specifications/staging-validation-monorepo/doc-1
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
- [ ] #1 overlays/rust/mise.toml 不再包含长 validation shell。
- [ ] #2 Rust adapter 不再枚举 capability Cartesian product。
- [ ] #3 docs-site 的 enabled/disabled 输出、任务和工具合同保持现有行为。
- [ ] #4 codecov-upload 的 Rust coverage tool、workflow、权限和 report 合同保持现有行为。
- [ ] #5 crates-io-publish 的任务、jq 工具、可执行发布脚本、CI package check 和 release publish 合同保持现有行为。
- [ ] #6 禁用 crates-io-publish 时，相关任务、工具、脚本和 workflow 行为仍完整缺席。
- [ ] #7 Rust adapter 可以通过 //overlays/rust:check 调用。
- [ ] #8 Rust profile-specific adapter tests 覆盖 crates.io capability 的启用和禁用路径。
- [ ] #9 根 check-templates rust 仍能把每个 capability case 传给该 adapter。
<!-- AC:END -->
