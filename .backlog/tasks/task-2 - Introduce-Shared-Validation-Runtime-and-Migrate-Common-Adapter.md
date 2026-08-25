---
id: TASK-2
title: Introduce Shared Validation Runtime and Migrate Common Adapter
status: To Do
assignee: []
created_date: '2026-08-25 10:04'
labels:
  - execution-ready
milestone: m-0
dependencies:
  - TASK-1
documentation:
  - .backlog/docs/specifications/staging-validation-monorepo/doc-1
type: enhancement
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Outcome

建立 Python validation runtime 和 profile-neutral shared checks，完成 common adapter 的行为等价迁移。common validation 继续验证 identity、docs-site、codecov-upload 和 coverage placeholder 合同，但不再依赖长内联 shell。

## Source

- Backlog document: `doc-1`
- Canonical path: `.backlog/docs/specifications/staging-validation-monorepo/doc-1 - Staging-Validation-Monorepo-Refactor.md`
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 runtime 能解析并约束 TEMPLATE_TOOL_ENABLED_CAPABILITIES。
- [ ] #2 runtime 提供统一的 staging context、命令执行和合同断言能力。
- [ ] #3 docs-site 的 enabled/disabled 检查在 common profile 上保持现有语义。
- [ ] #4 codecov-upload 的 enabled/disabled 检查在 common profile 上保持现有语义。
- [ ] #5 common coverage placeholder 的内容和失败行为保持不变。
- [ ] #6 common adapter 的 bootstrap 命令顺序和最终 mise run check 行为保持不变。
- [ ] #7 overlays/common/mise.toml 只保留 task registration 和 metadata。
- [ ] #8 common adapter 可以通过 //overlays/common:check 调用。
- [ ] #9 common profile 的直接 adapter 测试覆盖至少一个启用和一个禁用 capability case。
<!-- AC:END -->
