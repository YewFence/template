---
id: m-0
title: "Staging Validation Monorepo Refactor"
---

## Description

重构 template monorepo 的 staging validation maintenance environment：启用 mise monorepo task topology，将 overlay validation 从内联 shell 迁移为可维护 adapter，保留 `template-tool` 的动态 staging orchestration，并提取稳定共享验证行为。

完整实施 spec：Backlog document `doc-1`，路径 `.backlog/docs/specifications/staging-validation-monorepo/doc-1 - Staging-Validation-Monorepo-Refactor.md`。

完成范围包括 mise namespaced overlay tasks、capability case 去重、shared validation modules、common/Go/Rust 专属 adapter、测试迁移和架构文档更新；不改变 template capability contract、生成模板用户-facing tasks 或 staging validation 的外部生命周期。
