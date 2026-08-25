---
id: TASK-5
title: Rewrite Validation Adapter Test Interfaces
status: To Do
assignee: []
created_date: '2026-08-25 10:11'
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
- [ ] #1 测试不再从 overlays/*/mise.toml 提取 tasks.check.run 作为主要执行入口。
- [ ] #2 capability parser、shared context 和合同断言有直接测试。
- [ ] #3 common、Go CLI、Rust adapter 都有 profile-specific enabled/disabled 测试。
- [ ] #4 shared docs-site 和 codecov-upload 行为不会在三个 profile 中重复维护同一套测试逻辑。
- [ ] #5 至少一个测试从仓库根目录通过 namespaced mise task 调用真实 adapter registration。
- [ ] #6 capability mismatch、未知 capability 和排序/重复输入等边界有覆盖。
- [ ] #7 uv run --project tools/template-tool pytest tools/template-tool/tests -v 通过。
- [ ] #8 测试失败时能指出 adapter/profile/capability case，而不是只报告 Bash exit code。
<!-- AC:END -->
