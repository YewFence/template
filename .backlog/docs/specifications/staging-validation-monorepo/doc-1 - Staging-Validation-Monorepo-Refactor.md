---
id: doc-1
title: Staging Validation Monorepo Refactor
type: specification
created_date: '2026-08-25 09:37'
updated_date: '2026-08-25 09:49'
tags:
  - staging-validation
  - mise
  - monorepo
  - refactor
---
# Staging Validation Monorepo Refactor

## Status

Proposed implementation specification.

## Source Identifier

- Backlog document: `doc-1`
- Canonical path: `.backlog/docs/specifications/staging-validation-monorepo/doc-1 - Staging-Validation-Monorepo-Refactor.md`

## Goal

重构 template monorepo 的 staging validation maintenance environment，让 mise 负责清晰、可发现的 monorepo task topology，让 `template-tool` 继续负责动态 staging 生命周期，让每个 template overlay 只拥有自己的 validation adapter 行为。

重构后，维护者可以从仓库根目录发现并显式调用 namespaced overlay tasks；模板 capability、staging 准备和验证行为不再在多个 shell 入口中重复声明；validation 的行为和测试不再依赖从 TOML 字符串中提取 shell 并交给 Bash 执行。

## Current Context

当前根 `mise.toml` 没有启用 `monorepo_root`。三个 `overlays/<name>/mise.toml` 各自内联一段很长的 `check` shell task，内容同时承担 capability 组合解析、输出合同验证、依赖状态生成、语言专属检查和最终模板检查。

`tools/template-tool/src/template_tool/cli.py` 已经根据 `templates.toml` 展开每个 profile 的完整 capability 布尔组合，创建 disposable staging，实例化模板，建立外部 Git 状态，并通过环境变量把排序后的 capability set 传给 overlay task。因此 overlay 不应再次枚举所有 capability 组合。

## Desired Architecture

### Mise monorepo topology

根 `mise.toml` 启用：

```toml
[settings]
monorepo_root = true
```

根任务继续承载 maintenance environment 的统一入口，例如 `render`、`sync:check`、`check` 和文档参考生成。

每个 overlay 注册一个可从根目录显式发现的 validation task：

- `//overlays/common:check`
- `//overlays/go-cli:check`
- `//overlays/rust:check`

验证实际使用的 namespaced task 语法、task discovery、task info 和 project graph 行为，并在仓库文档中记录稳定用法。根 `check` 仍由 Python orchestration 展开动态 capability cases，不把每个 case 建模成静态 mise dependency。

### Validation adapter ownership

每个 overlay 的 `mise.toml` 只保留 task 注册和 task metadata；复杂实现移到 overlay-owned validation adapter，例如：

- `overlays/common/validation/check.py`
- `overlays/go-cli/validation/check.py`
- `overlays/rust/validation/check.py`

adapter 的外部 interface 是接收 staging template root 和 `TEMPLATE_TOOL_ENABLED_CAPABILITIES`，执行该 profile 的静态合同验证、必要的依赖引导、语言专属检查以及 staged template 自己的 `mise run check`。

adapter 不拥有 capability 矩阵展开、临时目录清理、模板渲染、project instantiation、外部 Git baseline 或全部 case 的失败汇总。

### Shared validation behavior

在 `tools/template-tool/src/template_tool/staging_validation/` 提取确实跨 profile 稳定的行为：

- capability environment 的解析和输入约束；
- mise、git 和文件系统操作的统一 context；
- task/tool/file/workflow 的可观察合同断言；
- `docs-site` 的 enabled/disabled 合同；
- `codecov-upload` 的跨 profile 合同。

共享模块必须通过 profile-neutral interface 工作，不按 template name 分支。common、Go 和 Rust 的真实差异继续由各自 overlay adapter 实现，包括 identity patterns、coverage report、语言 coverage tool、crates.io 发布和容器镜像发布。

### Single sources of truth

- `templates.toml`：profile capabilities、默认状态、capability-owned outputs、slot bindings，以及必要的 validation metadata。
- `mise.toml`：maintenance task topology 和 adapter registration。
- Python staging validation modules：共享验证实现。
- overlay adapter：profile-specific 验证行为和命令顺序。

禁止在 `templates.toml`、Python 和 shell 中分别维护 capability 组合列表。validation metadata 可以声明数据，例如 coverage report、identity forbidden patterns 和 profile-specific expected tools；不能把任意 shell 或验证流程编码成配置解释器。

## Scope

### In scope

- 启用并验证 mise monorepo project discovery。
- 将 overlay validation task 从内联 shell 迁移为可维护的 adapter implementation。
- 删除 overlay 中按 capability 组合枚举的长 `case`。
- 提取稳定的 shared validation context、assertions、`docs-site` 和 `codecov-upload` behavior。
- 保留 common、Go CLI、Rust 的 profile-specific adapter 和命令顺序。
- 重写 validation adapter tests，使主要测试直接跨 Python adapter interface。
- 保留至少一个薄的 mise namespaced task integration test。
- 更新 `CONTEXT.md`、`docs/architecture/monorepo.md`、相关 ADR 或维护文档中的 validation terminology 和调用示例。
- 保证默认 template snapshots 不被 validation bootstrap 状态污染。

### Out of scope

- 改变 template capability resolver 的语义或 `templates.toml` profile contract。
- 把动态 capability matrix、disposable staging 或 Git lifecycle 迁移到 mise task graph。
- 把 common、Go、Rust 的真实构建矩阵强行合并成一个 profile-name branching validator。
- 修改生成模板的用户-facing mise task、锁文件、Action digest 或项目 bootstrap contract。
- 引入远程 CI 服务、外部 registry 发布或真实 Codecov/GHCR/crates.io 发布。
- 创建非默认 capability snapshot。
- 修改 Git 历史、远端仓库、Issue、Pull Request 或评论。

## Migration Constraints

采用 expand–migrate–contract，保证每个阶段可验证：

1. 先启用并验证 monorepo task topology，同时以行为等价方式建立 adapter 新入口。
2. 把现有 overlay shell 按 profile 迁移到 adapter implementation，期间保留可回滚的调用路径，直到集成测试覆盖新入口。
3. 删除重复的 capability case 和已迁移的内联 shell。
4. 提取共享模块并把重复测试替换为共享 interface 测试。
5. 最后更新文档并运行完整的 repository checks。

每个阶段都必须保持根级 renderer/sync checks 可运行；涉及完整 staging 的检查继续交给 GitHub Actions 的 `mise run check` 矩阵执行。

## Acceptance Criteria

- 根 `mise.toml` 声明 `monorepo_root = true`，`mise tasks ls --all` 能发现三个 overlay validation tasks。
- 三个 overlay task 可以从仓库根目录使用 namespaced task 语法显式调用，并且 task info 指向对应 overlay adapter。
- `overlays/*/mise.toml` 不再包含数百行 validation shell，也不再枚举 capability Cartesian product。
- 根 `check-templates` 仍然为每个 profile 展开完整 capability 组合，并将排序后的显式 capability set 传给正确 adapter。
- shared validation behavior 在 common、Go CLI、Rust 三个 profile 上保持现有 enabled/disabled 语义，包括 docs-site 和 codecov-upload 合同。
- Rust crates.io 和 Go container image 专属行为仍只在对应 overlay adapter 中验证，common coverage placeholder 语义不被改变。
- validation tests 不再需要从 TOML 中提取 task shell 并用 `/bin/bash -c` 作为主要测试 interface；测试覆盖 parser、shared behavior、profile-specific behavior 和 namespaced task integration。
- `uv run --project tools/template-tool pytest tools/template-tool/tests -v` 通过。
- `mise run sync:check` 通过，且 `templates/<name>/` 没有因 validation bootstrap 产生非预期修改。
- 架构文档准确描述 mise topology、template-tool orchestration 和 overlay adapter 的职责边界。
- 所有新增 execution ticket 都能引用本文件的稳定 source identifier，并带有 `execution-ready` label。

## Verification Commands

```bash
mise tasks ls --all
mise tasks info //overlays/rust:check
mise tasks graph
uv run --project tools/template-tool pytest tools/template-tool/tests -v
mise run sync:check
```

完整的 `mise run check [template]` staging validation 由 GitHub Actions 执行，不要求维护者在本地生成或提交锁定状态。

## Design Notes

这是 maintenance environment 的重构，不是 template deliverable 的功能变更。mise monorepo 能力用于表达 task discovery、namespacing 和静态 topology；Python 仍然是动态 staging orchestration 的 owner。两者之间的 seam 是 overlay validation adapter 的单一调用入口，而不是一组通过 mise dependency graph 传递临时路径和 capability 参数的细碎任务。
