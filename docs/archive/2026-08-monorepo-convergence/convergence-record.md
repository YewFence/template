# Monorepo 配置收敛记录

> 历史材料：本文档保存收敛期间的实现合同、验证记录和决策表，包含已取代或撤销的方案。当前实现依据见 [`docs/architecture/monorepo.md`](../../architecture/monorepo.md) 和 [`docs/adr/`](../../adr/)。

## 状态

本文档记录 monorepo 中 mise、模板交付物和模板 workflow 的收敛合同。
其中“模板依赖状态”章节已在 2026-08-06 设计转向后取代旧的锁文件回写方案；旧方案只保留在 Git 历史中，不再作为实现依据。

## 当前范围

实施范围已经覆盖三个模板的 `mise.ci.toml`、结构化 Renovate、公共 workflow、声明式项目实例化、未引导模板交付物、disposable staging validation 和 monorepo 根 CI；旧的事务式 `locks:update`、来源回写与模板 Action updater 已删除。

workflow 只拥有触发器、权限、并发、缓存、平台矩阵与 mise 启动基础设施；项目检查、审计、版本和打包行为通过稳定 mise 任务调用。shared layout 只暴露已经证明存在真实差异的语义 slot，大型 Go/Rust 发布矩阵保持完整 adapter。

## 设计依据

- `mise.toml` 提供日常开发所需的稳定任务接口。
- `mise.ci.toml` 提供自动化和维护场景所需的额外工具与任务。
- `mise.ci.toml` 不属于 GitHub Actions 私有实现；维护者必须能够通过 `mise -E ci run <task>` 在本地运行和诊断其中的行为。
- workflow 应调用稳定的 mise 任务，不理解语言工具、命令组合或项目内部实现；环境选择、工具安装和锁文件完整性检查是允许直接调用 mise CLI 的基础设施特例。
- shared 来源只拥有模板无关的行为；Go、Rust 和 common 的真实差异通过 overlay adapter 提供。
- slot 按行为语义划分，不按文本位置或 step 序号建立细碎插入点。只有两个以上模板确实存在不同工具集合、依赖合同或完整实现时才建立 seam；真实差异可以由标量 slot 或完整 job adapter 表达。

## 已确认决策

### 1. `mise.ci.toml` 的语义

`mise.ci.toml` 表示“自动化与维护场景才需要的额外工具和任务”，不局限于 GitHub Actions。

由此得到以下合同：

- 日常任务保留在 `mise.toml`，例如 `check`、`fix`、`test`、`build` 和 `docs:*`。
- 在线 action 版本检查、依赖安全审计和 release helper 放在 `mise.ci.toml`。
- CI 环境中的任务必须能够在本地通过 `mise -E ci run <task>` 执行。
- workflow 只是任务调用方，不成为这些行为的事实来源。
- shared release helper 依赖的 `git-cliff` 应由共享 `mise.ci.toml` 声明；Go 不再单独从基础 `mise.toml` 提供这项依赖。

### 2. 统一审计接口

三个模板统一暴露以下审计入口：

```text
mise -E ci run audit
```

各模板 adapter 的职责如下：

- common：提供明确的 `[PLACEHOLDER]` 审计实现。
- Go：组合现有的 `mod:verify` 和 `vuln:check`。
- Rust：执行 `cargo audit --deny warnings`。

基础 `mise run check` 不隐式执行安全审计，避免日常检查依赖额外维护工具或在线漏洞数据。
common 当前位于基础 `mise.toml` 的 placeholder `audit` 将迁移到 `mise.ci.toml`。

`mod:verify` 和 `vuln:check` 可以作为 Go adapter 的内部任务保留，但 workflow 和其他外部调用方只依赖统一的 `audit` 接口。

### 3. Action 检查接口

当前存在两类不同性质的 action 检查：

- 基础环境中的离线检查：`actionlint` 与 `actions:pin-offline:check`。
- CI 环境中的在线策略检查：`actions:pin:check` 与 `actions:outdated`。

保留离线静态检查与在线版本检查两个层次：

```text
mise run actions:check
mise run actions:update
mise -E ci run actions:versions:check
```

接口语义如下：

- `actions:check` 位于普通 `mise.toml`，组合离线 pin 校验与静态 `actionlint`，是日常、确定性的只读检查。
- `actions:update` 是维护者主动执行的写操作，继续位于基础 `mise.toml`。
- `actions:versions:check` 是允许使用 `PINACT_GITHUB_TOKEN` 的在线版本策略检查，组合 `actions:pin:check` 和 `actions:outdated`。
- CI 环境不覆盖基础 `actions:check` 的语义。

## 已确认的实现边界

### Shared `mise.ci.toml` 的 slot interface

shared layout 暴露四个 slot：

```text
maintenance_tools
audit_tasks
release_version_tasks
release_package
```

边界如下：

- `maintenance_tools`：可选。Go 注入 `govulncheck`；Rust 注入 `cargo-audit` 和 `cargo-edit`；common 不需要绑定。
- `audit_tasks`：必填。common 提供 placeholder；Go 提供组合审计；Rust 提供 Cargo 审计。
- `release_version_tasks`：可选。当前只有 Rust 提供 `release:version:update`。
- `release_package`：必填。common 提供 placeholder，Go 和 Rust 提供各自的打包 adapter。

shared layout 直接拥有公共的 `git-cliff`、在线 action 版本检查，以及模板无关的 release helper。
不设置 `go_tools`、`rust_tasks`、`before_release` 或 `extra_tasks` 等按模板身份或文本位置划分的 slot。

mise 原生支持任务级 `tools`，但本设计不采用该方式。CI 环境的额外工具继续集中在顶层 `[tools]` 中，通过 `maintenance_tools` 注入，使工具目录和版本在生成后的 `mise.ci.toml` 中保持集中可见。

### Release helper 的共享边界

common、Go 和 Rust 当前具有内容一致的以下 release helper：

```text
release:version
release:tag
release:notes
release:changelog
release:tag:create
```

已确认由 shared layout 完整拥有这些任务，并在首次收敛时保持现有命令、输入、输出和失败行为不变。

模板差异只通过已经确认的 slot 进入：

- Rust 通过 `release_version_tasks` 提供 `release:version:update`。
- common、Go 和 Rust 分别通过 `release_package` 提供打包 adapter。
- 所有模板共同使用 shared 声明的 `git-cliff`。

首次收敛不为 release helper 提供模板级覆盖 slot，也不同时调整 tag 生成、release notes 模式、CHANGELOG 写入或已有 tag 检查逻辑。行为优化留到共享来源建立并通过等价验证之后单独讨论。

### Adapter 的退出与输出语义

common 的 `audit` 和 `release:package` 当前是显式 `[PLACEHOLDER]`，输出替换提示并以成功状态退出。Go 和 Rust adapter 执行真实命令，并将底层工具的失败状态直接返回给调用方。

已确认首次收敛继续保持以下语义：

- common placeholder 输出包含 `[PLACEHOLDER]` 的明确提示并成功退出；完整模板仍需先由 staging 验证流程生成通用依赖状态与 Action digest，不能把 placeholder 自身成功误写为未引导模板直接绿色。
- placeholder 不输出伪造的审计结果、版本或资产路径，只说明需要替换或在不需要该能力时删除。
- Go 的 `audit` 按 `mod:verify`、`vuln:check` 的顺序串行执行并 fail fast，保持当前 workflow 的执行顺序。
- Rust 的 `audit` 直接传播 `cargo audit` 的退出状态和输出。
- Go 和 Rust 的 `release:package` 直接传播打包脚本的退出状态和输出。
- shared layout 不为 adapter 增加统一的错误吞并、fallback 或输出包装。

### 模板依赖状态与临时验证

模板交付物不保存预生成依赖状态。`shared/`、`overlays/<name>/static/` 和 `templates/<name>/` 不提交模板的 `mise.lock`、`mise.ci.lock`、`Cargo.lock`、`go.sum`、`docs/pnpm-lock.yaml` 等原生命令输出；模板 workflow 不保存 Action commit digest，只声明 `actions/*@vN` 等兼容版本线。根 `mise.lock`、`tools/template-tool/uv.lock` 和根 workflow digest 属于 monorepo 维护环境，继续精确锁定。

模板声明生态认可的兼容版本线：稳定生态通常声明 major，pre-1.0 工具可保留 minor 兼容线，Go Modules 等不支持范围的生态继续使用具体合法版本。Rust `rust-version`、Go language directive 和项目自身版本表达兼容性或项目身份，不属于依赖锁定。

刚 render 或 apply 的结果是未引导模板，不保证直接通过 `mise run check`。用户需要在应用后依次生成 mise 锁、规范化语言依赖、生成文档锁并通过 pinact 固定 Action digest；完成后才成为应当通过检查的已引导项目。模板不增加 `mise run bootstrap` 聚合任务，文档直接列出真实命令。

已引导项目必须把生成状态提交到自己的 Git 仓库，包括 `mise.lock`、`mise.ci.lock`、语言锁定或校验状态、`docs/pnpm-lock.yaml` 和 pinact 修改；这些路径不得被忽略。模板继续使用 locked、frozen 和 pinned 检查，取消的只是模板维护者提前替未来用户解析依赖。

新项目引导与 staging validation adapter 运行 `deps:update`，解析执行当天兼容版本线内的当前版本；`deps:fix` 继续只做规范化。Go 使用更新加 tidy 处理必须具体声明的 module 版本，Rust 在没有 lockfile 时建立当前兼容解析。已有项目应用流程不自动升级依赖。

文档站点继续使用 pnpm 和 `docs/pnpm-lock.yaml`。aube 原生 `aube-lock.yaml` 尚不受 Renovate npm manager 的 lockfile maintenance 支持，因此本方案按 CLI 回退规则保留 pnpm，不同时生成两种锁文件。

validation adapter 生成文档 lockfile 后不运行 `docs:build`，只执行模板内置 `mise run check`。文档站点实际构建目前不属于模板基础验证合同。

文档任务分为 `docs:install`（非 frozen 的首次解析与安装）、`docs:lock`（只写 `pnpm-lock.yaml`）和 `docs:install:locked`（只消费已提交锁）。`docs:build`、`docs:dev` 与 `docs:preview` 统一依赖 `docs:install:locked`，防止消费任务修改依赖状态。

`init-project` 先由外部工具完成项目实例化；新项目随后按 trust、生成 mise 锁、locked 安装基础工具、`deps:update`、`docs:install`、Action pinning、hooks 安装和最终 `check` 的顺序完成依赖引导。validation adapter 用 `docs:lock` 代替文档安装并丢弃 staging。生成项目不再提供 Go 专属项目身份 `init`。

项目实例化是把通用模板蓝图一次性物化为具体项目树的外部工具能力，覆盖项目名称、描述、GitHub owner、仓库名及语言专属 module、crate 或 binary 身份。`init-project` 面向干净的新仓库，自动实例化临时模板树后再 staged apply；`apply-template` 面向已有项目，只做纯 staged apply，不自动重写项目身份、remote 或 Git 历史。最终模板不再携带需要运行后删除的 Go `mise run init` 或 `tools/init-template`。

`init-project` 使用显式 CLI options 作为稳定、可脚本化的 metadata 接口。交互式终端允许提示补齐缺失的必填项；非交互环境缺项直接失败。提示文本和顺序不构成兼容 API，工具不读取 Git remote 来猜测项目身份。字段集合由 D60 固定，staging validation fixture 由 D65 固定。

metadata schema 分成共享项目身份与 profile 专属语言身份。共享必填字段为 `--project-name`、`--description`、`--github-owner` 和 `--repo-name`；Go CLI 额外要求 `--go-module`、`--binary-name`，Rust 额外要求 `--cargo-package`、`--binary-name`，common 没有额外字段。`project-name` 是显示名称，不复用为语言标识符；CLI 根据所选模板只暴露和校验相关字段。

模板蓝图只保留一个带 metadata 占位符的 `README.md`，不再维护 `README.md` 模板指南与 `README.template.md` 项目内容双文件。`init-project` 在临时树中原地实例化 README；`apply-template` 不自动实例化或特殊消费它，只按普通模板文件执行 staged apply 并交给用户审查。统一模板使用说明归根 README，overlay README 只保留模板特有内容。

根 `README.md` 是统一的外部使用入口，负责应用器命令、metadata 参数和依赖引导；`overlays/<name>/static/README.md` 只保留各模板的功能介绍、结构说明和语言特有行为，不重复应用器流程。

Go 蓝图删除 `tools/init-template`、`tools/apply-existing` 和 `[tasks.init]`，不保留兼容入口。项目实例化与已有项目应用分别由正式外部 `init-project`、`apply-template` 承担，validation adapter 也不再维护嵌套 `tools/apply-existing` module 的依赖状态。

`init-project` 使用 clean-target apply policy：目标已是干净、unborn 且无 untracked 内容的新仓库，因此完整应用实例化后的 `README.md`、`AGENTS.md`、`.gitignore`、许可证、notice 和其他模板文件；已有项目 denylist 只属于 `apply-template`。两个入口共享 sparse fetch、临时 commit 和 squash apply 内核，但 protected policy 按目标生命周期分开。

`apply-template` 不接受 metadata，也不实例化内容或路径。已有项目的 staged tree 可以保留合法 uppercase blueprint token，包括 tokenized 路径；应用不会因此失败。成功输出必须给出未实例化 HINT 和 Git/token 搜索审查命令，但不启动交互式替换。

项目实例化使用严格 token engine，而不是对生成树再次运行 Jinja2。工具替换显式声明的 `{{UPPER_SNAKE_CASE}}` token，处理可识别的 UTF-8 文本和相对路径组件；未知 uppercase token 在替换后残留即失败。路径替换先生成完整计划，路径值必须是安全单组件，拒绝 `/`、`\\`、空值、`.`、`..` 与控制字符，且拒绝越界、碰撞和文件/目录类型冲突。GitHub Actions 表达式和其他双大括号内容不参与，语言差异通过 profile token map 与声明式派生值表达，不允许模板注入 imperative hook。

`templates.toml` 扩展为 render、apply 和 instantiate 共用的模板 profile 合同。每个 `[templates.<name>]` profile 从当前应用器静态支持的 metadata 字段中选择必填集合，并声明 token map、有限派生值以及专属 validation fixture；fixture 只用于 staging，不是 CLI 默认值。Python 工具不按 common、go-cli 或 rust 名称分支执行不同实例化流程，但当前版本静态定义自己支持的字段和 transform 词汇。

实例化 schema 保持最小：`required` 字段列表、平面 `tokens` 映射、有限 `derived` 声明和 `validation.metadata` 值。第一版不把 prompt、help、默认值、regex 或命令插值写进 profile；CLI help 与交互提示由当前应用器版本的静态 argparse 定义提供。

`init-project` 一次解析当前版本静态支持的全部命名 options，不根据远端配置动态生成 argparse。profile 只负责选择必填字段与 token 映射；无关 option、未知字段、未知 token source 或未知 transform 直接失败。应用器与不同版本模板 schema 不提供兼容保证，裸 `--help` 不联网并展示当前版本的完整参数集合。

`apply-template` 与 `init-project` 都要求显式 `--ref`，不默认使用 `main`。uvx 使用时，文档要求包来源 `@<ref>` 与模板 `--ref <ref>` 一致；clone 本地运行使用 `--repo <path> --ref HEAD`。工具不验证版本相等，也不适配错配 schema。

第一版 derived 白名单只有 `hyphen-to-underscore` 和 `json-string`。前者用于 Cargo package 到 Rust crate identifier 的转换；后者产生可直接放入 TypeScript/YAML 字符串位置的带引号转义值。raw 与编码上下文使用不同 token，不允许 transform 链、任意表达式或模板自定义编码器。

Token 语义不再混用：`PROJECT_NAME` 是显示名称，`PROJECT_DESCRIPTION`/`PROJECT_DESCRIPTION_JSON` 分别是 raw/JSON 描述，`GITHUB_OWNER` 与 `REPO_NAME` 是 GitHub 身份，`GO_MODULE` 是 Go module path，`CARGO_PACKAGE` 是 Cargo package 名，`RUST_CRATE_IDENT` 是源码 identifier，`BINARY_NAME` 是可执行文件、命令路径和 release packaging 名。Go 的 `cmd/your-cli`、completion 与命令文档属于 `BINARY_NAME` 迁移范围。

来源清理不依赖运行时兼容分支：身份相关的 `your-cli`、`rust-template`、`rust_template`、`github.com/example/your-cli` 等 legacy sentinel 必须在 manifest、源码、测试、mise task、脚本、docs package 和路径中显式迁成 token；残留字面量由外层 overlay validation adapter 暴露，而不是由实例化器猜测替换或进入用户项目检查。

各 `overlays/<name>/mise.toml` 在依赖生成和最终项目检查前扫描实例化 staging，拒绝该模板自己的 legacy identity sentinel。历史名称列表不进入 shared、生成模板或 `template-tool`，命中即 fail fast。

metadata 与 validation fixture 统一要求非空单行字符串，拒绝 NUL、ASCII 控制字符和前导/尾随空白；工具不静默 trim 或规范化字符，普通空格、标点和 Unicode 原样保留。第一版不在 Python 中实现生态命名正则，格式错误交给实例化后的原生工具与项目检查。

AGENTS 采用单文件策略：overlay 只交付面向生成项目的 `AGENTS.md`，模板维护者说明迁出模板；`init-project` 在临时树中原地实例化，`apply-template` 继续保护 `AGENTS*`，不自动替换或合并已有项目的 agent 规则。

根 CI 每周运行一次 staging validation，重新解析当前兼容版本线并执行同一模板检查；它不自动写回来源或创建依赖更新 PR，失败只作为维护者人工调整的信号。

每周 validation 明确排除 audit 与 release 演练。漏洞检查由已引导项目自己的 scheduled audit 负责，release helper 和平台打包由独立测试覆盖；定时任务只报告基础模板健康。

根 CI 第一版移除依赖模板锁文件和固定模板 workspace 的 Go/Rust 项目缓存，只保留 mise 工具缓存。生成项目自己的语言缓存继续存在；staging 专用缓存等出现真实性能问题后再设计。

每个 `overlays/<name>/mise.toml` 提供 monorepo-only 的验证 adapter，完整拥有该模板“生成临时状态并检查”的语言差异和执行顺序；它不是生成模板的一部分。Python 工具只负责临时 render、隔离 mise 与 Git 环境、调用 adapter、聚合错误并删除 staging，不理解 Cargo、Go、pnpm 或 pinact 的具体命令。

验证流程如下：

1. Python 在临时目录生成完整的未实例化模板。
2. 根工具使用固定、合成的 validation metadata 调用与 `init-project` 相同的项目实例化管线，使 staging 表示一个具体项目而不是含占位符的原始蓝图。
3. Python 为已经实例化的 staging 建立只服务于检查的外部 Git dir/index，使 Git-based 检查看到最终路径与内容。
4. 根工具从对应 overlay 启动验证 adapter，设置 `MISE_CEILING_PATHS=<monorepo-root>`、`MISE_GLOBAL_CONFIG_FILE=/dev/null` 和 overlay/staging 临时 trusted paths，不修改用户持久 trust 状态。
5. adapter 在 staging 中运行 `mise -E ci lock`、模板专属依赖规范化、文档 lock 和 Action pinning，然后运行 staging 模板自己的 `mise run check`。
6. validation fixture、锁文件、校验文件和 workflow digest 修改不回写任何真实来源或模板快照；流程结束后直接删除 staging。

因此删除 `templates.toml` 的 `[templates.<name>.locks]`、根 `locks:update` 任务与 CLI、Python 的允许输出/回写/回滚逻辑。普通 `render` 与 `sync:check` 仍只处理声明式来源和未引导模板快照，不运行原生命令；根 CI 的模板 job 不再执行 `install --locked` 后检查已提交锁文件，而是调用上述临时验证流程。

`locks:update` 不保留只读兼容别名。根 `check` 是 staging 生成与模板检查的唯一入口，命令名不再暗示 monorepo 会保存依赖更新结果。

根 `actions:update` 直接调用 pinact 更新 `.github/workflows/**`，删除 Python actions updater、CLI 和事务测试。shared、overlay 与模板快照保持兼容版本线，不参与根 digest 回写或 render。

### 三层检查边界

1. **未引导模板快照**：`render` 生成兼容版本线和未固定 Action 引用，不承诺 `mise run check` 通过。
2. **模板项目检查**：用户或验证 adapter 先生成依赖状态与 Action digest，再运行最终模板的 `mise run check`；模板自身仍保留 locked/frozen 的只读消费语义。
3. **快照同步检查**：根级 `sync:check` 只比较 shared、overlay 来源和 `templates/<name>` 快照，不运行依赖生成命令。

## 已完成的后续收敛

- `ci.yml` 共享 layout 固定三个 job，只通过 project cache slot 保留语言构建缓存差异；pnpm 文档缓存由 shared 直接拥有。独立 `audit.yml` 共享审计协议，通过路径、最小工具安装和缓存 slot 保留语言差异。
- `docs.yml` 共享 Pages 骨架并直接拥有 `node pnpm` 工具选择与 pnpm store 缓存，不再暴露 overlay slot。
- `prepare-release.yml` 共享 release PR 协议，Rust 独立更新 Cargo 版本文件。
- `release.yml` 共享 version、publish 和关闭旧 PR 协议，Go/Rust 完整 build matrix 作为大 adapter。
- 根 Renovate 与三模板配置仍由同一 base/profile module 生成，但根 profile 只维护 monorepo 自身环境；模板来源与快照均不由根 Renovate 自动更新。
- 根 `actions:update` 只通过 pinact 固定 monorepo 根维护 workflow；shared、overlay 和模板快照保留兼容版本线，不进入根更新范围。
- 根 CI 分离 source/common/go-cli/rust job，调用稳定根任务并保留语言缓存。

## 现状验证记录

- `mise run sync:check` 已确认 common、Go 和 Rust 生成快照均处于同步状态。
- template-tool 的 19 个单元与本地 Git 集成测试全部通过，覆盖 renderer、严格项目实例化、已有项目 apply、clean-target `init-project`、nested sparse path、冲突恢复与 markerless Git validation；旧锁回写和模板 Action 回写测试已经随实现删除。
- `apply-template` 保持纯 staged apply，保护已有项目的根级身份与工作区控制文件，不接收 metadata；`init-project` 使用完整 clean-target policy，不跳过实例化后的模板路径。两个入口均要求显式 `--ref`。
- 正式 `init-project` 已从当前工作树构造的临时 Git 源初始化 common、go-cli、rust 三份干净 unborn repository，分别产生 24、27、29 个 staged 路径；单个无父初始提交、完整 README/AGENTS、Go module/命令路径、Rust package/crate/binary、零冲突、无 `MERGE_HEAD`、无未知 token 与 legacy sentinel 全部通过。
- 三个模板已改为未引导蓝图；common、go-cli、rust 的 validation adapter 都在 disposable staging 中实例化 fixture、生成 mise/语言/pnpm 状态、固定 Action 并运行模板自身检查，真实验证全部通过且未修改来源或生成快照。
- `[templates.<name>.locks]`、根 `locks:update`、Python 允许输出/回写/回滚实现与模板 Action updater 已删除；依赖生成和 pinact 修改只存在于临时 staging，根维护环境的锁文件与 workflow digest继续保留。
- 三个模板的 release helper 已在 `MISE_OFFLINE=1` 的临时 Git 仓库演练：`release:version`/tag 统一得到 `0.1.0`/`v0.1.0`，notes、changelog、tag 创建与重复创建通过；common placeholder 生成零附件，Go/Rust package adapter 各生成一个 Linux x86_64 tar.gz。测试使用 Git plumbing 建历史并隔离用户全局 Git 配置，不接触任何远端或正式 tag。
- 根级 `MISE_OFFLINE=0 mise run check` 完整检查约 99 秒，本地与 CI 超时必须覆盖该时长。
- 模板检查通过外部 `GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE` 提供真实 baseline，不写 `templates/<name>/.git`；忽略缓存不入 index，Go 嵌套 Git 测试显式隔离父级 Git 环境。
- 根配置与三个模板配置已通过官方 `renovate/renovate:44.13.2` 容器中的 `renovate-config-validator --strict --no-global`；容器使用无网络、只读 bind mount 和默认非 root 用户。
- 公开 sparse fetch、uvx 安装和 `v0.1.0` release/tag 未在本地阶段执行，需未来获得明确远端操作授权。

## 决策记录

| 编号 | 决策 | 状态 |
| --- | --- | --- |
| D1 | `mise.ci.toml` 表示可本地运行的自动化与维护环境 | 已确认 |
| D2 | 三个模板统一使用 `mise -E ci run audit` | 已确认 |
| D3 | 普通 `mise.toml` 保留离线 `actions:check`，`mise.ci.toml` 提供在线 `actions:versions:check` | 已确认 |
| D4 | shared `mise.ci.toml` 使用 `maintenance_tools`、`audit_tasks`、`release_version_tasks` 和 `release_package` 四个 slot | 已确认 |
| D5 | shared 完整拥有五个公共 release helper，首次收敛只迁移所有权、不改变行为 | 已确认 |
| D6 | common placeholder 成功退出，真实 adapter 直接传播失败，Go 审计串行 fail fast | 已确认 |
| D7 | 锁文件由完整模板配置生成，普通 render 不运行原生锁文件命令 | 已取代：只在 staging 生成 |
| D8 | `templates.toml` 只配置允许输出；固定的 `locks:update` 任务名和语言命令都不进入模板 profile | 已取代：删除 locks 配置与任务 |
| D9 | 第一版所有 `locks.outputs` 固定回写 `overlays/<name>/static`，不写入 shared；`generated/` 方案撤销 | 已取代：不回写任何来源 |
| D10 | `generated/` 第一版只允许保存锁文件生成结果 | 已撤销 |
| D11 | 模板 `locks:update` 注册在普通 `mise.toml` | 已撤销 |
| D12 | `locks.outputs` 表示允许更新的完整依赖状态路径集合，可包含 manifest | 已取代：删除 outputs 合同 |
| D13 | 模板项目 `mise run check` 只消费已提交锁文件，不调用 monorepo 的 `locks:update` | 已取代：先生成临时状态再检查 |
| D18 | 不额外暴露真实锁文件生成 smoke-test task，也不纳入普通 PR 检查；真实生成由主动维护流程触发 | 已取代：普通模板检查即执行临时生成 |
| D14 | overlay 根部的 monorepo-only `mise.toml` 提供 `locks:update` 命令组 | 已取代：提供完整 `check` adapter |
| D15 | overlay `locks:update` 接收一个模板根目录位置参数和可选 `--bump` flag，并只修改该 staging 目录 | 已取代：`check` 接收 staging 根目录 |
| D16 | shared `mise.ci.toml` layout 的四个 slot 采用固定 TOML 落点 | 已确认 |
| D17 | 普通 `check` 不跨环境验证 CI 工具，不新增 `ci:tools:check` 或 `locks:check`；workflow 直接调用 mise CLI 验证 CI 环境锁文件 | 已取代：外层 check 先生成 CI 锁 |
| D19 | overlay 锁文件 adapter 只运行一次 `mise -E ci lock`，同时生成 `mise.lock` 与 `mise.ci.lock` | 保留为 validation adapter 步骤 |
| D20 | `locks:update` 默认保留已有 mise 版本解析；显式 `--bump` 时才重新解析模糊工具选择器 | 已取代：未引导模板每次从兼容线解析 |
| D21 | 三个 overlay adapter 统一通过 staging 模板的 mise 环境执行 `pnpm install --lockfile-only`，与最终模板的日常 pnpm 任务使用同一工具 | 已确认 |
| D22 | Go adapter 对根 module 和 `tools/apply-existing` 运行 `go mod tidy` | 已被 D61 取代：删除嵌套工具 |
| D23 | Rust adapter 使用 `cargo generate-lockfile`，不使用 `cargo update`，允许输出不包含 `Cargo.toml` | 已确认 |
| D24 | common adapter 只维护 mise 与文档锁文件，不调用 placeholder 项目依赖任务 | 已确认 |
| D25 | staging 保留已有依赖状态文件；首次允许输出可在执行前缺失，但 adapter 成功后必须全部存在 | 已取代：staging 从未引导快照开始 |
| D26 | 越界修改检测复用 renderer 文件树快照，不创建临时 Git 仓库，也不忽略任何未声明路径 | 已取代：生成状态允许留在 staging |
| D27 | `locks.outputs` 最终必须是 staging 内的普通、不可执行文件；拒绝目录和 symlink，不自研内容解析 | 已取代：删除 outputs 合同 |
| D28 | `locks:update` 任一阶段失败时恢复调用前的 overlay 与模板目录；成功完成全部验证后才提交更新 | 已取代：从不修改真实目录 |
| D29 | adapter 使用 ceiling、禁用全局配置和进程级双路径临时信任，不修改用户 mise trust 状态 | 已确认 |
| D30 | Go、Cargo 与 pnpm 都从 staging 模板 mise 配置解析；overlay 不重复声明工具版本 | 已确认 |
| D31 | `locks:update` 尊重调用者的 mise auto-install 与 offline 设置，缺工具时失败，不回退到未声明系统工具 | 已取代：validation adapter 继承调用者策略 |
| D32 | 删除冗余的 `locks.task` 配置；根工具直接依赖统一的 overlay adapter interface | 已取代：删除 locks interface |
| D33 | `ci.yml`、`docs.yml`、`prepare-release.yml` 和 `release.yml` 使用 shared layout；只把真实语言缓存、版本文件和完整构建矩阵通过语义 adapter 保留，共同 pnpm 行为由 shared 直接拥有 | 已实施 |
| D34 | 根 Renovate 与三模板配置由 base/profile module 生成，根配置忽略 `templates/**` | 已取代：根配置同时停止扫描 shared/overlay 模板来源 |
| D35 | 根 `actions:update` 只更新根/shared/overlay 真实来源，并对回写、render 和同步检查提供回滚 | 已取代：模板来源保持兼容线，根工具只固定维护 workflow |
| D36 | 根 CI 直接维护，分离 source/common/go-cli/rust job，不从 shared render | 已实施 |
| D37 | Rust 独立 audit 只保留 schedule/manual，并调用 `mise -E ci run audit` | 已实施 |
| D38 | 模板检查不写 `.git` 标记，使用外部 Git dir/index；忽略缓存不入 baseline，嵌套 Git 测试清理父级 Git 环境 | 已实施 |
| D39 | `init-project` 只 bootstrap 干净 unborn repository，创建普通初始根提交后复用 `apply-template` 的 Git 应用内核 | 已实施；protected policy 由 D64 细化 |
| D40 | 模板交付物不包含预生成锁文件或 Action digest；维护环境继续精确锁定 | 已确认 |
| D41 | 未引导模板不保证绿色，生成依赖状态与 Action digest 后才进入可检查状态 | 已确认 |
| D42 | 版本声明使用生态认可的兼容版本线，而不是机械 major | 已确认 |
| D43 | 最终模板不增加 `mise run bootstrap`，用户文档列出真实引导命令 | 已确认 |
| D44 | overlay 的 monorepo-only `check` adapter 拥有临时状态生成与模板检查顺序 | 已确认 |
| D45 | Python 只管理 staging、隔离、调用和清理，不回写生成状态 | 已确认 |
| D46 | 根 Renovate 只维护 monorepo 自身环境；模板兼容版本线人工维护，生成项目 Renovate 继续负责用户项目 | 已确认 |
| D47 | 已引导项目提交全部生成锁定状态，并继续执行 locked、frozen 和 pinned 检查 | 已确认 |
| D48 | 新项目引导与 staging 验证运行 `deps:update` 解析当前兼容版本；已有项目不自动升级 | 已确认 |
| D49 | 文档站点继续使用 pnpm；aube 因 Renovate 不支持其原生锁文件而回退 | 已确认 |
| D50 | staging 生成文档 lockfile，但普通模板验证不运行 `docs:build` | 已确认 |
| D51 | 根 CI 每周定时运行 staging validation；失败不自动回写或创建 PR | 已确认 |
| D52 | 每周 validation 不运行 audit 或 release，只检查基础模板健康 | 已确认 |
| D53 | 文档任务拆分为 install、lock、install:locked；build/dev/preview 只依赖 locked 安装 | 已确认 |
| D54 | 用户与 validation 的依赖引导顺序固定；其中“Go init 位于工具安装后”的部分已由 D58 取代 | 部分被取代 |
| D55 | 删除 `locks:update` 且不保留兼容别名；根 `check` 是唯一 staging 验证入口 | 已确认 |
| D56 | 第一版删除根 CI 的模板语言缓存，只保留 mise 工具缓存 | 已确认 |
| D57 | 根 `actions:update` 直接调用 pinact；删除 Python actions updater 与事务测试 | 已确认 |
| D58 | 项目实例化归 `template-tool`；`init-project` 自动完整实例化，`apply-template` 保持纯 staged apply | 已确认 |
| D59 | `init-project` 以 CLI options 为正式 metadata 接口；TTY 可补问，非交互缺项失败且不猜 remote | 已确认 |
| D60 | metadata 使用共享必填字段加 profile 专属字段；显示名、仓库身份与语言标识符分离 | 已确认 |
| D61 | 蓝图只保留一个占位符 README；删除 Go 两个一次性工具与 init task，apply 不自动实例化 README | 已确认 |
| D62 | 根 README 统一承载外部使用说明；overlay README 只介绍模板特有功能和结构 | 已确认 |
| D63 | 蓝图只保留一个项目规则 `AGENTS.md`；删除 `AGENTS.template.md`，apply 继续保护 `AGENTS*` | 已确认 |
| D64 | `init-project` 使用 clean-target apply policy 完整应用实例化模板；已有项目 denylist 只属于 `apply-template` | 已确认 |
| D65 | staging validation 先用固定合成 metadata 复用项目实例化管线，再由 overlay adapter 生成状态并检查 | 已确认 |
| D66 | 实例化使用严格 uppercase token engine；不二次运行 Jinja，不提供语言专属 imperative hook | 已确认 |
| D67 | `templates.toml` 是 render/apply/instantiate 的 profile 合同；应用器版本静态定义支持的字段/transform 词汇 | 已确认；由 D71 细化静态 CLI |
| D68 | 实例化 schema 采用最小形状，不引入字段对象 DSL、默认值或命令插值 | 已确认；help 来自静态 CLI |
| D69 | derived 白名单首版仅含 `hyphen-to-underscore`、`json-string`；不同上下文使用独立 token | 已确认 |
| D70 | metadata 必须非空单行且无控制/边缘空白；不静默规范化，不复制生态命名正则 | 已确认 |
| D71 | `init-project` 使用静态 argparse；profile 只选择必填字段与映射，不保证跨版本模板 schema 兼容 | 已确认 |
| D72 | `apply-template`、`init-project` 的 `--ref` 必填；文档显式对齐应用器与模板 ref，不验证兼容 | 已确认 |
| D73 | strict token engine 同时替换内容和相对路径；路径计划先验证安全、无越界且无冲突 | 已确认 |
| D74 | token 语义分离显示名、描述、GitHub 身份、语言 package/module、crate identifier 与 binary 名 | 已确认 |
| D75 | 删除身份相关 legacy sentinel；实例化器不提供按旧字面量替换的兼容分支 | 已确认 |
| D76 | legacy identity 检查归各 overlay 的 monorepo-only validation adapter，不进入模板或 `template-tool` | 已确认 |
| D77 | `apply-template` 保留内容/路径 token 为 staged changes；不接收 metadata，输出未实例化审查 HINT | 已确认 |
