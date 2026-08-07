# Monorepo 公开发布计划

## 状态

本地 monorepo 收敛已经完成。renderer、模板实例化、Git 应用器、共享 workflow、Renovate 生成、staging validation 和本地 release helper 演练均已落地。

当前计划只跟踪需要远端或公开发布权限的剩余工作。历史迁移阶段和已撤销方案保存在 [`docs/archive/2026-08-monorepo-convergence/`](../archive/2026-08-monorepo-convergence/) 中。

## 完成条件

- 正式仓库可以通过公开 Git 和 uvx 路径获取。
- 首个不可移动的 `v0.1.0` tag 与 GitHub Release 完成端到端验证。
- common、Go 和 Rust 模板的 release 行为符合本地验证结果。
- 新 monorepo 成为唯一维护入口，旧仓库不再接收功能、依赖更新或 release。
- 旧仓库历史、tag 和已有 release 不被重写。

## 待执行

1. 创建或确认正式仓库 `YewFence/template`，添加官方 remote，并验证默认分支和访问权限。
2. 从公开地址验证 sparse fetch、`uvx` 安装、`apply-template` 和 `init-project`。
3. 在 GitHub Actions 中运行根 CI，确认 source、common、go-cli 和 rust 检查均通过。
4. 演练 release PR、不可移动的 `v0.1.0` tag 和 GitHub Release。
5. 验证 common 不发布附件，Go 和 Rust 发布预期平台资产，release notes 能标明受影响模板。
6. 公开验证通过后，将 monorepo 宣布为唯一维护入口，不设置双写期。
7. 归档旧 GitHub Go 模板仓库；按既定边界处理 Forgejo 和 Rust 来源，不导入或改写旧 tag namespace。
8. 更新仓库链接和使用说明，确认旧入口不会继续接收自动更新或 release。

## 暂不包含

- 模板重复 apply 或自动升级协议。
- 将三个模板重新拆分为独立发布版本。
- Josh、反向镜像或独立过滤仓库视图。
- 自动创建更新 PR 或自动归档旧仓库。

这些能力只有在公开使用暴露真实需求后才重新设计。
