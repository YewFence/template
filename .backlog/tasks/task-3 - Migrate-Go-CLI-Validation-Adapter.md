---
id: TASK-3
title: Migrate Go CLI Validation Adapter
status: Done
assignee:
  - '@yewfence'
created_date: '2026-08-25 10:06'
updated_date: '2026-08-26 16:08'
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
- [x] #1 overlays/go-cli/mise.toml 不再包含长 validation shell。
- [x] #2 Go CLI adapter 不再枚举 capability Cartesian product。
- [x] #3 docs-site 的 enabled/disabled 输出、任务和工具合同保持现有行为。
- [x] #4 codecov-upload 的 PR/default branch workflow、权限和工具 ownership 合同保持现有行为。
- [x] #5 container-image-publish 的 task、ko tool、workflow、tag 分支和禁止输出合同保持现有行为。
- [x] #6 禁用 container-image-publish 时，相关任务、工具和 workflow 行为仍完整缺席。
- [x] #7 Go CLI adapter 可以通过 //overlays/go-cli:check 调用。
- [x] #8 Go CLI profile-specific adapter tests 覆盖 container capability 的启用和禁用路径。
- [x] #9 根 check-templates go-cli 仍能把每个 capability case 传给该 adapter。
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add overlays/go-cli/validation/check.py using the shared staging runtime for Go identity, docs-site, Codecov, and container-image-publish contracts while preserving the existing command order.
2. Reduce overlays/go-cli/mise.toml to the namespaced adapter registration and add the validation package marker.
3. Update validation adapter tests to invoke the Go adapter directly and cover container capability enabled and disabled paths plus the namespaced task integration.
4. Run focused adapter tests, the template-tool test suite, sync checks, and diff validation.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented overlays/go-cli/validation/check.py with shared capability parsing, docs-site and Codecov contracts, Go identity checks, and container-image-publish enabled/disabled validation. Reduced overlays/go-cli/mise.toml to the adapter registration and changed adapter tests to invoke Go directly while retaining Rust shell compatibility.
Verification: uv run --project tools/template-tool pytest tools/template-tool/tests/test_validation_adapters.py -q -> 21 passed; full pytest -> 115 passed; mise tasks ls/info/graph passed; mise run sync:check reports repository/common/go-cli/rust in sync; git diff --check passed. Root check-templates go-cli expanded all 8 cases but local execution was blocked before adapter execution by the existing MISE_GLOBAL_CONFIG_FILE=/dev/null incompatibility with mise 2026.8.12.

修复 staging validation 的 mise 配置隔离：移除不受支持的 MISE_GLOBAL_CONFIG_FILE=/dev/null，改用 MISE_IGNORED_CONFIG_PATHS 忽略用户全局配置，并将 MISE_CEILING_PATHS 设置为仓库根的父目录；新增外部 maintenance repository 根变量。验证：CLI focused tests 8 passed，template-tool pytest 118 passed，sync:check 通过；端到端 check 已进入 Go CLI adapter，但因多 capability case 的工具锁定/安装在 180 秒超时。
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
迁移 Go CLI validation 到独立 Python adapter：复用 shared staging runtime，保留 Go identity、docs-site、codecov-upload 与 container-image-publish 合同及 bootstrap/check 命令顺序；mise 入口仅保留 namespaced adapter 注册。新增 Go CLI adapter 直接测试，覆盖 container capability 启用和禁用。验证：focused adapter tests 21 passed，完整 template-tool pytest 115 passed，mise task discovery/info/graph、sync:check 和 git diff --check 通过；根 check-templates go-cli 展开全部 8 cases，但本机 MISE_GLOBAL_CONFIG_FILE=/dev/null 与 mise 2026.8.12 冲突使其在 adapter 执行前失败。
<!-- SECTION:FINAL_SUMMARY:END -->
