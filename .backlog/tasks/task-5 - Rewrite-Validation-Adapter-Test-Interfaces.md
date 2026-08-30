---
id: TASK-5
title: Rewrite Validation Adapter Test Interfaces
status: Done
assignee:
  - '@yewfence'
created_date: '2026-08-25 10:11'
updated_date: '2026-08-30 16:29'
labels:
  - execution-ready
milestone: m-0
dependencies:
  - TASK-2
  - TASK-3
  - TASK-4
documentation:
  - .backlog/docs/specifications/staging-validation-monorepo/doc-1
type: enhancement
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Outcome

重写 validation adapter 测试接口，使测试直接跨 Python adapter 和 shared validation interface 工作；TOML shell 提取与 `/bin/bash -c` 不再是主要测试路径，同时保留一层薄的 mise namespaced task 集成测试。

## Source

- Backlog document: `doc-1`
- Canonical path: `.backlog/docs/specifications/staging-validation-monorepo/doc-1 - Staging-Validation-Monorepo-Refactor.md`
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 测试不再从 overlays/*/mise.toml 提取 tasks.check.run 作为主要执行入口。
- [x] #2 capability parser、shared context 和合同断言有直接测试。
- [x] #3 common、Go CLI、Rust adapter 都有 profile-specific enabled/disabled 测试。
- [x] #4 shared docs-site 和 codecov-upload 行为不会在三个 profile 中重复维护同一套测试逻辑。
- [x] #5 至少一个测试从仓库根目录通过 namespaced mise task 调用真实 adapter registration。
- [x] #6 capability mismatch、未知 capability 和排序/重复输入等边界有覆盖。
- [x] #7 uv run --project tools/template-tool pytest tools/template-tool/tests -v 通过。
- [x] #8 测试失败时能指出 adapter/profile/capability case，而不是只报告 Bash exit code。
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Extract staged-project fixture, mise shim, and adapter invocation from test_validation_adapters.py into a shared tests/staging_harness.py so docs-site/codecov staging logic has a single maintenance point (AC#4).
2. Expand test_staging_validation.py with direct StagingContext and validate_docs_site / validate_codecov_upload contract tests using the harness (AC#2).
3. Add profile-specific tests: common coverage-placeholder contract enabled/disabled (AC#3) and codecov-upload capability-mismatch tests parametrized across profiles (AC#6).
4. Add one integration test that runs the real adapter registration through the namespaced mise task from the repository root (AC#5).
5. Make adapter failures diagnostic: a dedicated failure type carries profile, capability case, and adapter stderr; mismatch tests assert stderr names the capability case (AC#8).
6. Run pytest, sync:check, and git diff --check; confirm no templates/ changes (AC#7).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Extracted staged-project fixture, mise recording shim, and adapter invocation into tools/template-tool/tests/staging_harness.py as the single maintenance point. Direct shared-interface tests now cover StagingContext, validate_docs_site, and validate_codecov_upload; profile-specific and mismatch/boundary tests stay parametrized in test_validation_adapters.py.
Namespaced integration test: to let the inner adapter mise calls hit the recording shim while the outer mise run stays real, overlay mise.toml tasks now inject PATH through mise's native env mechanism: [env] _.path = { path = [get_env(name='TEMPLATE_TOOL_VALIDATION_BIN', default='/var/empty')] }. Mechanism verified with an isolated monorepo experiment before applying; unset variable leaves task PATH unchanged.
AdapterFailure carries profile, capability case, and adapter stderr; mismatch tests assert stderr names the capability. Reordered validate_codecov_upload enabled branch so a missing coverage task reports 'codecov-upload enabled but ...' instead of a bare workflow-job message.
Verification: uv run --project tools/template-tool pytest tools/template-tool/tests -q -> 152 passed (119 before); focused staging/adapters files -> 60 passed; mise run sync:check -> repository/common/go-cli/rust in sync; mise tasks ls --all shows all three overlay checks; mise tasks info //overlays/common:check points at the adapter; git diff --check clean; no templates/ changes.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Rewrote validation adapter test interfaces: primary tests now invoke the Python adapters directly against a shared staging harness (staging_harness.py), with direct shared-interface tests for the capability parser, StagingContext, docs-site and Codecov contracts, profile-specific enabled/disabled coverage for common/Go/Rust (crates.io, container image, coverage placeholder), mismatch/unknown/duplicate/ordering boundary cases, and one thin integration test that runs the real adapter registration through the namespaced mise task from the repository root via mise's native [env] _.path injection. Failures now report the adapter, profile, capability case, and stderr instead of a bare exit code. Verified with 152 pytest tests (up from 119), sync:check in sync, mise task discovery/info/graph, git diff --check, and no templates/ changes.
<!-- SECTION:FINAL_SUMMARY:END -->
