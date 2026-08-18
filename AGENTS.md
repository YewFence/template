# Repository Guide

## 仓库用途

这个仓库维护 `common`、`go-cli` 和 `rust` 三个工程模板，以及渲染、实例化、验证和应用这些模板所需的维护基础设施。

它不是某个生成项目本身。根 `AGENTS.md` 面向 monorepo 维护者；`overlays/<name>/static/AGENTS.md` 才是对应 template deliverable（模板交付物）中的项目规则，并会进入 `templates/<name>/AGENTS.md`。不要把根维护规则渲染进生成项目，也不要用生成项目的规则替代本文件。

## 开始工作前

1. 阅读根 [`CONTEXT.md`](CONTEXT.md)，使用其中定义的 Template System 术语。
2. 阅读与任务相关的 [`docs/architecture/`](docs/architecture/) 和 [`docs/adr/`](docs/adr/)。

## 目录职责

- `shared/static/`：多个模板完全一致、可直接复制的公共文件。
- `shared/layouts/`：拥有完整输出结构的共享 Jinja layout。
- `shared/fragments/`：绑定到语义 slot 的公共 fragment。
- `shared/renovate/`：生成模板 Renovate 配置的公共来源。
- `overlays/<name>/static/`：单个模板拥有的文件。
- `overlays/<name>/fragments/`：单个模板提供的 adapter fragment。
- `overlays/<name>/mise.toml`：只供 monorepo staging validation 使用，不进入 template deliverable。
- `overlays/<name>/README.md`：面向模板使用者的模板说明，不进入 template deliverable。
- `templates/<name>/`：renderer 生成的完整、自包含默认 capability 集合 preview。
- `templates.toml`：render、slot、project instantiation 和 apply profile 的共享合同。
- `tools/template-tool/`：renderer、staging validation、project instantiation 和 Git apply 实现。
- `scripts/apply-template`：没有 uv 时使用的 best-effort Bash fallback，不是首选入口。
- `config/` 与根 `.github/`：monorepo maintenance environment（维护环境）的直接配置。

## 修改规则

不要直接编辑 `templates/<name>/`。共享行为改在 `shared/`，模板专属行为改在对应 `overlays/<name>/`，然后通过 renderer 重新生成快照。

Template capability 属于 template profile 合同，不是 project identity metadata。Capability-owned output 与 conditional/variant slot binding 声明在 `templates.toml` 中；不要把 capability 条件散入 Jinja、source 目录名称或 Python 的 template-name 分支。只提交默认 capability 集合的 preview，非默认组合由 disposable staging 验证，不生成额外 snapshot。

只有多个模板确实共享稳定行为时，才把内容提升到 `shared/`。layout 的 slot 必须按行为语义命名；不要创建按文本位置、step 序号或模板名称划分的通用插入点。Go、Rust 和 common 的真实工具、缓存、审计、版本文件和构建矩阵差异应保留为 overlay adapter，必要时保留完整实现。

template deliverable 刚生成时处于 unbootstrapped template（未引导模板）状态。不要向 `shared/`、`overlays/` 或 `templates/` 添加预生成的 mise、Go、Cargo、pnpm 锁定状态或 GitHub Action digest。bootstrapped project（已引导项目）自行生成并提交这些状态；monorepo 只在 disposable staging 中生成它们进行验证。

monorepo maintenance environment 与 template deliverable 分开管理。根 `mise.lock`、`tools/template-tool/uv.lock` 和根 workflow Action digest 必须保持精确锁定。不要手工编辑锁文件，使用 mise、uv、Go、Cargo、pnpm 或对应原生工具更新。

`init-project` 和 `apply-template` 是不同生命周期的入口。前者只为干净的新仓库执行 project instantiation 并完整应用模板；后者只为已有历史的干净仓库产生 staged changes，不自动改写项目身份、remote 或 Git 历史。不要根据目标仓库状态隐式切换这两个模式。

## 常用工作流

首次准备 maintenance environment 时运行：

```bash
mise install
```

修改模板来源后运行：

```bash
mise run render [template]
mise run sync:check [template]
```

- `render` 重新生成一个或全部模板快照。
- `sync:check` 只读验证来源和未实例化快照同步。
- `check` 为适用 capabilities 展开完整布尔组合，创建 disposable staging，复用 `init-project`、`apply-template` 共用的模板准备内核与正式 project instantiation，调用对应 validation adapter 生成临时状态，再运行模板自己的完整检查。这个不需要本地跑，交由 Github Action 负责检查。

修改 `tools/template-tool/` 后，运行：

```bash
uv run --project tools/template-tool python -m unittest discover -s tools/template-tool/tests -v
mise run sync:check
```

CLI 的 help 文本（description、epilog、参数说明）变化会影响生成的 CLI 参考，同步运行：

```bash
mise run docs:reference
```

## 文档导航

- [`README.md`](README.md)：面向模板使用者的功能列表与使用入口。
- [`CONTEXT.md`](CONTEXT.md)：Template System 的术语表；命名设计、文档和测试时使用这里的规范术语。
- [`docs/README.md`](docs/README.md)：完整文档索引。
- [`docs/guides/use-template.md`](docs/guides/use-template.md)：面向模板使用者的完整使用指南。
- [`docs/reference/cli.md`](docs/reference/cli.md)：由 `mise run docs:reference` 生成的 CLI 参考，不要手改。
- [`docs/architecture/monorepo.md`](docs/architecture/monorepo.md)：当前来源模型、组合方式、渲染、staging validation、项目实例化和自动化所有权。
- [`docs/adr/`](docs/adr/)：仍然有效的长期架构决策及其取舍。
- [`docs/plans/`](docs/plans/)：尚未完成的活跃工作，只保留未来步骤。

## Agent skills

- [`docs/agents/repository-tracker.md`](docs/agents/repository-tracker.md)：仓库共享工作使用 GitHub Issues；执行 Issue、Pull Request、原生关系或 spec 发布操作前先阅读。
- [`docs/agents/domain.md`](docs/agents/domain.md)：探索代码、命名领域概念或评估架构决策前先阅读。

## 外部操作

本地读取、编辑、渲染和测试可以直接进行。创建或修改远端仓库内容、Issue、PR、评论、tag、GitHub Release，推送提交，以及归档旧仓库，都需要用户明确授权；不要把本地发布计划当成远端操作许可。
