---
id: TASK-1
title: Enable Mise Monorepo Validation Task Topology
status: Done
assignee:
  - '@yewfence'
created_date: '2026-08-25 10:03'
updated_date: '2026-08-25 10:37'
labels:
  - execution-ready
milestone: m-0
dependencies: []
documentation:
  - .backlog/docs/specifications/staging-validation-monorepo/doc-1
type: enhancement
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Outcome

启用 maintenance environment 的 mise monorepo task topology，让三个 overlay validation task 可以从仓库根目录被发现并通过 namespaced task 显式调用，同时保持现有 validation 行为。

## Source

- Backlog document: `doc-1`
- Canonical path: `.backlog/docs/specifications/staging-validation-monorepo/doc-1 - Staging-Validation-Monorepo-Refactor.md`
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 根 mise.toml 声明 monorepo_root = true。
- [x] #2 mise tasks ls --all 能发现 common、Go CLI、Rust 三个 overlay validation task。
- [x] #3 mise tasks info 能显示每个 task 的 overlay 来源和 usage。
- [x] #4 从仓库根目录调用 namespaced overlay task 时，现有 adapter 仍能接收 template_root 和 capability environment。
- [x] #5 根 check-templates 的动态 capability matrix 行为没有改变。
- [x] #6 mise tasks graph 不报告由本次 topology 变更引入的错误。
- [x] #7 不修改 templates/<name>/ 的生成快照或 bootstrap 状态。
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add monorepo_root = true to the maintenance root mise.toml.
2. Register each overlay validation task as a namespaced monorepo task while preserving its current adapter shell and usage contract.
3. Invoke the namespaced overlay task from template-tool with the existing template root and capability environment.
4. Document the stable topology and run task discovery, task info, graph, focused adapter tests, and sync checks.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented monorepo topology with top-level monorepo_root = true and [monorepo].config_roots = ["overlays/*"].
Updated template-tool to invoke //overlays/<template>:check from the repository root while preserving template_root and TEMPLATE_TOOL_ENABLED_CAPABILITIES.
Added architecture documentation and a CLI integration assertion for the namespaced task contract.
Verification: mise tasks ls --all discovered all three overlay tasks; mise tasks info showed each overlay source and usage; mise tasks graph and mise tasks validate passed; mise run sync:check reported repository/common/go-cli/rust in sync; uv run --project tools/template-tool pytest tools/template-tool/tests -q passed 108 tests; git diff showed no templates/ changes.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Enabled mise monorepo task discovery for the maintenance environment, registered and documented the three namespaced overlay validation tasks, and switched template-tool staging checks to invoke those tasks from the repository root with the existing capability environment. Verified task discovery/info/graph/validation, 108 template-tool tests, sync:check, and an unchanged templates/ tree.
<!-- SECTION:FINAL_SUMMARY:END -->
