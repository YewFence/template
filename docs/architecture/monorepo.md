# Monorepo 架构

本仓库是 `common`、`go-cli` 和 `rust` 三个工程模板的唯一事实来源。维护者编辑共享来源和模板专属来源，renderer 生成完整、自包含的 template deliverable（模板交付物）；生成项目在运行时不依赖本 monorepo。

相关架构取舍记录在 [`docs/adr/`](../adr/) 中，历史收敛过程记录在 [`docs/archive/2026-08-monorepo-convergence/`](../archive/2026-08-monorepo-convergence/) 中。

## 来源模型

```text
shared/                 模板无关的共享来源
├── static/             可直接复制的公共文件
├── layouts/            拥有完整输出结构的 Jinja layout
├── fragments/          可复用的 slot fragment
└── renovate/           Renovate 公共配置

overlays/<name>/        单个模板拥有的来源
├── static/             模板专属文件
├── fragments/          模板专属 adapter fragment
└── mise.toml           只供 monorepo staging validation 使用

templates/<name>/       renderer 生成的完整模板快照
templates.toml          profile、render、slot、实例化和 apply 合同
tools/template-tool/    渲染、验证、实例化和 Git 应用实现
```

`shared/` 只拥有各模板确实共享的行为。Go、Rust 和 common 的工具、缓存、审计、版本文件及构建矩阵等真实差异保留在对应 overlay 中。

`templates/<name>/` 是派生结果，不应直接编辑。快照必须完整、自包含，并能从 `shared/`、`overlays/` 和 `templates.toml` 确定性重建。

## 组合模型

完全一致且无需参数化的内容使用 `shared/static/`。模板专属内容使用 `overlays/<name>/static/`。

需要共享整体结构、但允许少量真实差异的文件使用 layout、slot 和 fragment：

1. shared layout 拥有完整输出文件的稳定结构。
2. layout 只暴露按行为语义命名的 slot。
3. shared 或 overlay fragment 为 slot 提供完整实现。
4. `templates.toml` 为每个输出和 profile 绑定 fragment。
5. renderer 在写入快照前验证未知 slot、缺失 slot、重复绑定和输出冲突。

slot 不按文本行、step 序号或模板名称划分。单个模板的大型真实差异应保留为完整 adapter，不通过大量细碎 slot 模拟任意文本拼接。

## 渲染与同步

根级 mise 提供三个维护入口：

```text
mise run render [template]
mise run sync:check [template]
mise run check [template]
```

`render` 从声明式来源重新生成一个或全部模板快照。写入采用 staging 和原子替换，并保留普通文件的 executable bit、路径边界与 symlink 安全约束。

`sync:check` 执行只读重建，将结果与 `templates/<name>/` 比较，用于发现手工修改或过期快照。它验证的是仍含 metadata token 的未实例化 blueprint，不生成依赖状态。

## 模板交付状态

刚生成的 template deliverable 处于 unbootstrapped template（未引导模板）状态。它包含 compatibility line（兼容版本线）声明和项目 metadata token，但不预提交未来项目的以下状态：

- `mise.lock` 与 `mise.ci.lock`；
- Go、Cargo 等语言依赖的锁定或校验状态；
- `docs/pnpm-lock.yaml`；
- GitHub Action digest。

`init-project` 完成 project instantiation（项目实例化）后，使用者通过真实生态命令生成并提交这些状态。bootstrapped project（已引导项目）继续使用 locked、frozen 和 pinned 检查保证可复现性。

monorepo 自身的维护环境与模板交付物分离。根 `mise.lock`、`tools/template-tool/uv.lock` 和根 workflow 的 Action digest 仍然精确锁定。

## Staging Validation

`mise run check [template]` 验证实例化后的真实项目行为，但不修改来源或模板快照：

1. renderer 在临时目录生成未实例化 blueprint。
2. 工具读取 `templates.toml` 中固定的 validation metadata，复用 `init-project` 的实例化引擎替换内容和路径 token。
3. 工具为 staging 建立外部 `GIT_DIR`、`GIT_WORK_TREE` 和 `GIT_INDEX_FILE`，不向模板目录写入 `.git`。
4. 对应 `overlays/<name>/mise.toml` validation adapter 生成临时 mise、语言、文档和 Action 状态。
5. validation adapter 运行模板自己的 `mise run check`。
6. 整个 staging 及生成状态在检查结束后丢弃。

Python 工具拥有临时目录、隔离环境、Git baseline、validation adapter 调用和清理。语言命令及其执行顺序由对应 validation adapter 拥有。

`sync:check` 与 staging validation 验证不同边界：前者验证来源能够确定性生成 blueprint，后者验证 blueprint 实例化并完成依赖引导后能够通过项目检查。

## 项目实例化

`templates.toml` 是 render、apply 和 instantiate 共用的 profile 合同。每个 profile 声明：

- 必填 metadata 字段；
- metadata 到 uppercase token 的映射；
- 有限的声明式派生值；
- 仅供 staging validation 使用的合成 metadata。

实例化引擎替换可识别 UTF-8 文本和相对路径组件中的显式 uppercase token。路径替换在执行前计算完整计划，拒绝越界、不安全组件和路径碰撞。当前派生 transform 仅包含 `hyphen-to-underscore` 与 `json-string`。

应用器使用静态 CLI 参数集合，不根据远端配置动态构造命令接口，也不承诺不同版本应用器与模板 schema 的任意组合兼容。

## 新项目与已有项目

`init-project` 面向干净、unborn 且目标路径就是仓库根目录的新 Git 仓库。它创建普通的无父初始提交，在临时模板树中完成项目身份实例化，再使用 clean-target policy 将完整模板应用为 staged changes。它不会创建 remote、绕过 identity、签名或 hooks，也不会提交模板内容。

`apply-template` 面向至少已有一个 commit 的干净 Git 仓库。默认要求显式 metadata，并只在临时 fetched template tree 中执行 project instantiation；它不会扫描、推断或替换目标仓库原有文件中的 token。`--keep-tokens` 显式保留未实例化 blueprint 行为。

两个入口共享 sparse fetch、临时无父模板 commit 和 Git squash apply 内核，但拥有不同的目标策略：

- `init-project` 完整应用实例化后的模板，包括 README、AGENTS、忽略规则和许可证。
- `apply-template` 跳过 `templates.toml` 中声明的根级身份与工作区控制路径，并提示使用者人工比较；实例化只影响传入模板树。

成功应用只留下 staged changes，不移动目标分支或创建提交。冲突时保留 index stages 和工作树现场，不创建 `MERGE_HEAD`。第一版不提供重复 apply、provenance 状态或模板升级协议。

## 自动化所有权

模板 workflow 只拥有触发器、权限、并发、缓存、平台矩阵及 mise 启动基础设施。项目检查、审计、版本和打包行为通过稳定 mise 任务调用，workflow 不复制项目内部命令组合。

根 `.github/workflows/` 只维护 monorepo 自身的生成同步、工具测试和 staging validation，不参与模板 workflow 的 render，避免维护 CI 依赖其自身生成结果。

根 Renovate 只维护 monorepo 环境，包括根 workflow、根 mise 状态和 `tools/**`。模板 blueprint 的兼容版本线由维护者审查；生成项目中的完整 Renovate 配置负责项目引导后的依赖更新和 lockfile maintenance。

## 文档所有权

根 [`README.md`](../../README.md) 是模板使用者的统一入口，说明 `apply-template`、`init-project` 和依赖引导流程。

`overlays/<name>/static/README.md` 只描述对应生成项目的功能、结构和语言行为。模板维护架构、决策、计划与历史记录全部保存在根 `docs/`，不会进入生成项目。
