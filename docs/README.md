# 文档

这里保存 monorepo 的当前架构、有效决策、活跃计划和历史记录。

## 当前系统

- [Monorepo 架构](architecture/monorepo.md)：当前来源模型、生成流程、验证边界和应用器职责。
- [架构决策](adr/)：解释难以从代码直接看出的长期取舍。

## 模板使用指南

- [Rust crates.io 发布](guides/rust-crates-io-publishing.md)：启用 `crates-io-publish` capability 后的首次配置与后续发布流程。

## 活跃工作

- [Monorepo 公开发布](plans/monorepo-publication.md)：远端创建、首个公开版本和旧仓库切换。

## 历史记录

- [2026-08 Monorepo 收敛](archive/2026-08-monorepo-convergence/)：最初计划、实施记录和包含已撤销方案的完整决策日志。
- [2026-08 Template export](archive/2026-08-template-export.md)：独立候选树导出入口的合同与实施记录。

阅读当前实现时，不要把 `archive/` 中的内容当作有效合同。历史记录与当前文档冲突时，以 `architecture/` 和未被取代的 ADR 为准。
