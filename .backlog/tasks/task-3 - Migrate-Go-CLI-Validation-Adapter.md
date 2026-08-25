---
id: TASK-3
title: Migrate Go CLI Validation Adapter
status: To Do
assignee: []
created_date: '2026-08-25 10:06'
labels:
  - execution-ready
milestone: m-0
dependencies:
  - TASK-2
documentation:
  - .backlog/docs/specifications/staging-validation-monorepo/doc-1
type: enhancement
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Outcome

让 Go CLI validation 使用 shared runtime，并保留 Go CLI 自己的 identity、docs-site、codecov-upload 和 container-image-publish 合同及命令顺序。

## Source

- Backlog document: `doc-1`
- Canonical path: `.backlog/docs/specifications/staging-validation-monorepo/doc-1 - Staging-Validation-Monorepo-Refactor.md`
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 overlays/go-cli/mise.toml 不再包含长 validation shell。
- [ ] #2 Go CLI adapter 不再枚举 capability Cartesian product。
- [ ] #3 docs-site 的 enabled/disabled 输出、任务和工具合同保持现有行为。
- [ ] #4 codecov-upload 的 PR/default branch workflow、权限和工具 ownership 合同保持现有行为。
- [ ] #5 container-image-publish 的 task、ko tool、workflow、tag 分支和禁止输出合同保持现有行为。
- [ ] #6 禁用 container-image-publish 时，相关任务、工具和 workflow 行为仍完整缺席。
- [ ] #7 Go CLI adapter 可以通过 //overlays/go-cli:check 调用。
- [ ] #8 Go CLI profile-specific adapter tests 覆盖 container capability 的启用和禁用路径。
- [ ] #9 根 check-templates go-cli 仍能把每个 capability case 传给该 adapter。
<!-- AC:END -->
