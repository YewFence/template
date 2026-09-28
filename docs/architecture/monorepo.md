# Monorepo 架构

本仓库是 `common`、`python`、`go-cli` 和 `rust` 四个工程模板的唯一事实来源。维护者编辑共享来源和模板专属来源，renderer 生成完整、自包含的 template deliverable（模板交付物）；生成项目在运行时不依赖本 monorepo。

相关架构取舍记录在 [`docs/adr/`](../adr/) 中。早期历史文档已在公开发布前移除，可通过 Git 历史追溯；已撤销的方案不构成有效合同。

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
├── validation/          profile-specific validation adapter
└── mise.toml           只供 monorepo staging validation 使用

templates/<name>/       renderer 生成的默认 capability 集合 preview
templates.toml          profile、render、slot、实例化和 apply 合同
tools/template-tool/    渲染、验证、实例化和 Git 应用实现
```

`shared/` 只拥有各模板确实共享的行为。Go、Rust 和 common 的工具、缓存、审计、版本文件及构建矩阵等真实差异保留在对应 overlay 中。

`templates/<name>/` 是派生结果，不应直接编辑。每份 preview 必须完整、自包含，并能从 `shared/`、`overlays/` 和 `templates.toml` 按 profile 的默认 capability 集合确定性重建；非默认组合不生成或提交额外 preview。

## Template Capability 合同

`templates.toml` schema v2 在每个 template profile 下以布尔表声明 capabilities。key 存在表示 capability 适用于该 profile，value 表示默认是否启用；名称使用 lowercase kebab-case。resolver 从默认集合出发应用显式 enable/disable override，并拒绝未声明 capability 或同一 capability 的冲突 override。

Template capability 是 project instantiation 前对 template deliverable 行为的选择，不属于 project identity metadata，不创建 metadata token 或持久 provenance。所有 profile 必须先完整验证 capability-owned outputs、conditional/variant slots 和每个分支，再解析 effective enabled set；关闭 capability 不能掩盖坏合同。

## 组合模型

完全一致且无需参数化的内容使用 `shared/static/`。模板专属内容使用 `overlays/<name>/static/`。

需要共享整体结构、但允许少量真实差异的文件使用 layout、slot 和 fragment：

1. shared layout 拥有完整输出文件的稳定结构。
2. layout 只暴露按行为语义命名的 slot。
3. shared 或 overlay fragment 为 slot 提供完整实现。
4. `templates.toml` 为每个输出和 profile 绑定 fragment。
5. profile 可以用 capability-owned output selector、conditional slot binding 或 variant slot binding 声明可选行为。
6. renderer 在写入 preview 前验证未知 slot、缺失 slot、重复绑定、selector overlap、所有 variant branch 和输出冲突。

slot 不按文本行、step 序号或模板名称划分。Capability 归属保存在 `templates.toml`，不通过 Jinja 条件、source 目录名称或 Python 中按模板名称分支表达。单个模板的大型真实差异应保留为完整 adapter，不通过大量细碎 slot 模拟任意文本拼接。

## 渲染与同步

根级 mise 提供三个维护入口：

```text
mise run render [template]
mise run sync:check [template]
mise run check [template]
```

根 `mise.toml` 启用 `monorepo_root = true`，因此 overlay validation adapter 通过各自 overlay 的 namespaced task 注册，从仓库根目录发现和显式调用：

```text
mise tasks ls --all
mise tasks info //overlays/common:check
mise run //overlays/common:check /tmp/staging/common
```

对应的 Python、Go CLI 和 Rust task 分别是 `//overlays/python:check`、`//overlays/go-cli:check` 与 `//overlays/rust:check`。这些 task 只接收 staging template root，并从 `TEMPLATE_TOOL_ENABLED_CAPABILITIES` 读取当前 case；完整 capability matrix 和 disposable staging 生命周期仍由 `template-tool` 的根 `check` task 管理。adapter 的共享 capability parser、命令 context 和合同断言位于 `tools/template-tool/src/template_tool/staging_validation/`，profile-specific 行为位于对应的 `overlays/<name>/validation/check.py`。

`render` 从声明式来源重新生成一个或全部 profile 的默认 capability 集合 preview。写入采用 staging 和原子替换，并保留普通文件的 executable bit、路径边界与 symlink 安全约束。

`sync:check` 执行默认 capability 集合的只读重建，将结果与 `templates/<name>/` 比较，用于发现手工修改或过期 preview。它验证的是仍含 metadata token 的未实例化 blueprint，不生成依赖状态，也不为非默认组合维护 expected tree。

## 模板交付状态

刚生成的 template deliverable 处于 unbootstrapped template（未引导模板）状态。它包含 compatibility line（兼容版本线）声明和项目 metadata token，但不预提交未来项目的以下状态：

- `mise.lock` 与 `mise.ci.lock`；
- Go、Cargo 等语言依赖的锁定或校验状态；
- `docs/pnpm-lock.yaml`；
- GitHub Action digest。

`init-project` 完成 project instantiation（项目实例化）后，使用者通过真实生态命令生成并提交这些状态。bootstrapped project（已引导项目）继续使用 locked、frozen 和 pinned 检查保证可复现性。

monorepo 自身的维护环境与模板交付物分离。根 `mise.lock`、`tools/template-tool/uv.lock` 和根 workflow 的 Action digest 仍然精确锁定。

## Staging Validation

`mise run check [template]` 验证实例化后的真实项目行为，但不修改来源或 template deliverable preview。它为每个 profile 自动展开适用 capabilities 的完整布尔笛卡尔积；当前共运行 24 个 cases：`common` 与 `python` 分别验证 `docs-site` 和 `codecov-upload` 的四种组合，`go-cli` 验证 `docs-site`、`container-image-publish` 与 `codecov-upload` 的八种组合，`rust` 验证 `docs-site`、`crates-io-publish` 与 `codecov-upload` 的八种组合。

1. 共享模板准备内核验证完整 profile 合同、解析 case 的 effective capability set，并在隔离 destination 渲染未实例化 blueprint。
2. 工具读取 `templates.toml` 中固定的 validation metadata，复用正式 project instantiation 引擎替换内容和路径 token。
3. 工具检查生成树仍处于 unbootstrapped template 状态，并为 staging 建立外部 `GIT_DIR`、`GIT_WORK_TREE` 和 `GIT_INDEX_FILE`，不向模板目录写入 `.git`。
4. 对应 overlay validation adapter（经 `overlays/<name>/mise.toml` 的 namespaced task 注册调用）从按名称排序的显式 capability set 生成临时 mise、语言、文档和 Action 状态。
5. adapter 验证 capability-specific 任务和输出的存在或缺席，运行对应检查及模板自己的完整 `mise run check`。
6. Python orchestration 汇总全部 case 结果，整个 staging 及生成状态在检查结束后丢弃。

Python 工具拥有临时目录、隔离环境、Git baseline、validation adapter 调用和清理。语言命令及其执行顺序由对应 validation adapter 拥有。

`init-project`、`apply-template`、`export-template` 与 staging validation 共享 selected-ref source/profile load、完整合同验证、capability resolve、隔离 destination render 和 metadata instantiation。准备完成后四个入口才分别进入 initial commit 与完整 apply、protected-path filtering 与 squash apply、同级 staging 的原子候选树发布、或者 disposable bootstrap 与检查。Staging 不通过应用 CLI 驱动 cases；入口的 Git 生命周期由各自 integration tests 覆盖。

`sync:check` 与 staging validation 验证不同边界：前者验证来源能够确定性生成默认 blueprint preview，后者验证每个 capability 组合的 blueprint 实例化并完成依赖引导后能够通过项目检查。

## 项目实例化

`templates.toml` 是 render、apply 和 instantiate 共用的 profile 合同。每个 profile 声明：

- 适用 template capabilities 及其默认状态；
- 必填 metadata 字段；
- metadata 到 uppercase token 的映射；
- 有限的声明式派生值；
- 仅供 staging validation 使用的合成 metadata。
- 面向使用者、覆盖全部 required metadata 的 export metadata。

Capability selection 与 metadata 相互独立，并先于 project instantiation 完成。实例化引擎替换可识别 UTF-8 文本和相对路径组件中的显式 uppercase token。路径替换在执行前计算完整计划，拒绝越界、不安全组件和路径碰撞。当前派生 transform 包含 `hyphen-to-underscore`、`json-string` 与 `toml-basic-string`。

应用器使用静态 CLI 参数集合，不根据远端配置动态构造命令接口，也不承诺不同版本应用器与模板 schema 的任意组合兼容。

## 新项目与已有项目

`init-project` 面向干净、unborn 且目标路径就是仓库根目录的新 Git 仓库。它先在临时模板树中完成 selected-ref 合同验证、渲染和项目身份实例化，随后创建普通的无父初始提交，再使用 clean-target policy 将完整模板应用为 staged changes。它不会创建 remote、绕过 identity、签名或 hooks，也不会提交模板内容。

`apply-template` 面向至少已有一个 commit 的干净 Git 仓库。默认要求显式 metadata，并只在 selected-ref source checkout 之外的临时渲染树中执行 project instantiation；它不会扫描、推断或替换目标仓库原有文件中的 token。`--keep-tokens` 显式保留未实例化 blueprint 行为。

两个入口共享 selected-ref 的整仓 shallow/partial fetch、临时无父模板 commit 和 Git squash apply 内核，但拥有不同的目标策略：

- `init-project` 完整应用实例化后的模板，包括 README、AGENTS、忽略规则和许可证。
- `apply-template` 跳过 `templates.toml` 中声明的根级身份与工作区控制路径，并提示使用者人工比较；实例化只影响传入模板树。

`export-template` 面向不修改任何现有项目的人工比较场景。它要求显式 `--ref` 与 `--template`，从 profile 默认 capability 集合和 `templates.toml` 中的 export metadata 开始应用 CLI 覆盖；交互模式最后编辑所有 metadata 字段。它把完整实例化树先写入 destination 同级 staging，所有准备成功后才原子发布到不存在或为空的 destination。它不要求、初始化或修改 Git 仓库，不创建临时模板 commit、index 或 manifest，不执行 protected-path filtering，也不承诺 diff、复制、合并、provenance 或升级协议。

成功应用只留下 staged changes，不移动目标分支或创建提交。冲突时保留 index stages 和工作树现场，不创建 `MERGE_HEAD`。第一版不提供重复 apply、provenance 状态或模板升级协议。

## 自动化所有权

模板 workflow 只拥有触发器、权限、并发、缓存、平台矩阵及 mise 启动基础设施。项目检查、审计、版本和打包行为通过稳定 mise 任务调用，workflow 不复制项目内部命令组合。

模板 GitHub Release workflow 在版本解析时固定 checkout commit SHA，构建和发布复用该 SHA，发布 job 按解析出的 tag 互斥。共享 `.github/scripts/publish-release.sh` 是 GitHub 平台 adapter：使用只读 API 查询 Release 和精确 tag ref、校验 tag 指向，再通过 `gh release create`、`upload` 和 `edit` 发布。只有 release PR 合并入口允许 GitHub 自动创建 tag，目标为该固定 SHA；tag push 和手动发布入口要求远端 tag 已存在。不再交付本地建 tag 的 `release:tag:create` task。

首次发布的附件、临时草稿、公开顺序和失败清理由 `gh release create` 管理。已有草稿和已发布 Release 的重跑覆盖生成的说明、prerelease 状态和同名附件，保留人工标题和额外附件；草稿在上传成功后公开。Latest 沿用 CLI 默认自动判定，不显式设置 `--latest`。不探测或绕过 GitHub immutable release 保护，不为重跑的部分失败增加回滚，也不主动删除既有 Release 或 tag。

根 `.github/workflows/` 只维护 monorepo 自身的生成同步、工具测试和 staging validation，不参与模板 workflow 的 render，避免维护 CI 依赖其自身生成结果。

根 Renovate 只维护 monorepo 环境，包括根 workflow、根 mise 状态和 `tools/**`。模板 blueprint 的兼容版本线由维护者审查；生成项目中的完整 Renovate 配置负责项目引导后的依赖更新和 lockfile maintenance。

## 文档所有权

根 [`README.md`](../../README.md) 是模板使用者的统一入口，说明 `export-template`、`apply-template`、`init-project` 和依赖引导流程。

`overlays/<name>/static/README.md` 只描述对应生成项目的功能、结构和语言行为。模板维护架构、决策、计划与历史记录全部保存在根 `docs/`，不会进入生成项目。
