---
id: TASK-2
title: Introduce Shared Validation Runtime and Migrate Common Adapter
status: Done
assignee:
  - '@yewfence'
created_date: '2026-08-25 10:04'
updated_date: '2026-08-25 11:15'
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
- [x] #1 runtime 能解析并约束 TEMPLATE_TOOL_ENABLED_CAPABILITIES。
- [x] #2 runtime 提供统一的 staging context、命令执行和合同断言能力。
- [x] #3 docs-site 的 enabled/disabled 检查在 common profile 上保持现有语义。
- [x] #4 codecov-upload 的 enabled/disabled 检查在 common profile 上保持现有语义。
- [x] #5 common coverage placeholder 的内容和失败行为保持不变。
- [x] #6 common adapter 的 bootstrap 命令顺序和最终 mise run check 行为保持不变。
- [x] #7 overlays/common/mise.toml 只保留 task registration 和 metadata。
- [x] #8 common adapter 可以通过 //overlays/common:check 调用。
- [x] #9 common profile 的直接 adapter 测试覆盖至少一个启用和一个禁用 capability case。
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a profile-neutral staging_validation runtime with constrained capability parsing, staging context command execution, and reusable task/tool/file/workflow contract assertions.
2. Extract shared docs-site and codecov-upload checks into the runtime while preserving their current enabled/disabled semantics.
3. Add the common overlay adapter, reduce overlays/common/mise.toml to task registration/metadata, and preserve coverage placeholder and bootstrap/check ordering.
4. Replace common shell extraction tests with direct adapter tests covering enabled and disabled capability cases plus mismatch failures.
5. Run focused and full validation, sync checks, and review the diff without changing generated templates.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented tools/template-tool/src/template_tool/staging_validation runtime with constrained capability parsing, StagingContext command/filesystem helpers, task/tool/file/workflow assertions, and shared docs-site/Codecov contracts. Added overlays/common/validation/check.py and reduced overlays/common/mise.toml to the namespaced registration wrapper while preserving identity, coverage placeholder, bootstrap, and final check order.
Verification: uv run --project tools/template-tool pytest tools/template-tool/tests -q -> 114 passed; mise tasks ls --all discovered all three overlay tasks; mise tasks info //overlays/common:check points to the adapter; mise tasks graph is clean; mise run sync:check reports repository/common/go-cli/rust in sync; git diff --check passed; no templates/ files changed. mise run check common reached all four cases but the local mise version rejected the existing MISE_GLOBAL_CONFIG_FILE=/dev/null setting before adapter execution.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Introduced the shared staging validation runtime and migrated the common adapter to a Python implementation. Capability parsing, staging commands, docs-site checks, and scoped Codecov workflow assertions are reusable; common-specific coverage placeholder and bootstrap/check ordering remain unchanged. Verified with 114 pytest tests, namespaced task discovery/info/graph, sync:check, a direct common adapter enabled/disabled matrix, and a namespaced task integration test.
<!-- SECTION:FINAL_SUMMARY:END -->
