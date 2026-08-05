# Monorepo 配置收敛讨论

## 状态

本文档用于同步记录 monorepo 中 mise 配置与模板 workflow 的收敛决策。
当前仍处于讨论阶段；只有标记为“已确认”的内容可以作为后续实现合同。

## 当前范围

本轮收敛三个模板的 `mise.ci.toml`，并同步实现它所依赖的 `locks:update [--bump] <template>` 基础设施、overlay monorepo-only 锁文件 adapter、原生锁文件更新和最终模板验证，形成可以在本地完整运行的稳定任务接口与可复现工具环境。

以下内容暂不纳入本轮实现：

- monorepo 根目录的 GitHub Actions workflow；等仓库主体完成后再添加。
- 三个模板的 `ci.yml` layout 与 fragment；先保留现有差异，待 mise 任务接口稳定后逐项讨论。
- release workflow 和 Renovate。

`ci.yml` layout、workflow 触发器、job 拓扑、缓存和审计 job 的收敛仍不属于本轮；现有 workflow 保持原样，等 mise 接口与锁文件流程稳定后再讨论。

未来的 GitHub Actions CI 只负责在 pull request 更新时再次调用已经通过本地验证的根级 mise 检查任务，不拥有额外的项目检查逻辑。mise 环境选择、工具安装和锁文件完整性属于 workflow 启动基础设施，可以直接调用 mise CLI，不包装成项目任务。

## 设计依据

- `mise.toml` 提供日常开发所需的稳定任务接口。
- `mise.ci.toml` 提供自动化和维护场景所需的额外工具与任务。
- `mise.ci.toml` 不属于 GitHub Actions 私有实现；维护者必须能够通过 `mise -E ci run <task>` 在本地运行和诊断其中的行为。
- workflow 应调用稳定的 mise 任务，不理解语言工具、命令组合或项目内部实现；环境选择、工具安装和锁文件完整性检查是允许直接调用 mise CLI 的基础设施特例。
- shared 来源只拥有模板无关的行为；Go、Rust 和 common 的真实差异通过 overlay adapter 提供。
- slot 按行为语义划分，不为单行工具配置或单个 workflow step 建立细碎插入点。

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

- common placeholder 输出包含 `[PLACEHOLDER]` 的明确提示并成功退出，使语言无关模板生成后可以直接通过基线检查。
- placeholder 不输出伪造的审计结果、版本或资产路径，只说明需要替换或在不需要该能力时删除。
- Go 的 `audit` 按 `mod:verify`、`vuln:check` 的顺序串行执行并 fail fast，保持当前 workflow 的执行顺序。
- Rust 的 `audit` 直接传播 `cargo audit` 的退出状态和输出。
- Go 和 Rust 的 `release:package` 直接传播打包脚本的退出状态和输出。
- shared layout 不为 adapter 增加统一的错误吞并、fallback 或输出包装。

### 锁文件的生成阶段与所有权

收敛后的三个 `mise.ci.toml` 都包含 shared 提供的 `git-cliff`，同时具有不同的维护工具集合：

- common：只有公共维护工具。
- Go：公共维护工具和 `govulncheck`。
- Rust：公共维护工具、`cargo-audit` 和 `cargo-edit`。

因此三个模板的完整原生锁文件必然不同，但不能在 mise 配置尚未完成时直接把锁文件当作独立静态来源设计。

实现已经补齐 renderer 之外的显式原生生成阶段：根级 `locks:update [--bump] <template>` 在 staging 模板中调用 overlay adapter，只允许声明输出变化，固定回写对应 overlay，并在切换后重新 render、同步检查和执行模板完整检查。普通 `render` 与 `sync:check` 仍保持离线、确定性，不隐式运行原生命令。

已确认采用显式的两阶段锁文件流程：

1. renderer 先在临时目录生成完整模板，使 shared layout 和 overlay adapter 已经组合成最终 `mise.toml` 与 `mise.ci.toml`。
2. `locks:update [--bump] <template>` 在该完整模板中运行 mise 原生命令，生成或更新完整的 `mise.lock` 与 `mise.ci.lock`。
3. 更新任务把原生生成的完整文件回写到对应的 `overlays/<name>/static/<path>`，不拆分或合并锁文件条目。
4. 更新任务重新 render 正式模板，再运行 `sync:check` 和模板检查。
5. 普通 `render` 和 `sync:check` 保持确定性、离线和无网络，不隐式运行 `mise lock`。

在这个模型中，锁文件是基于完整模板配置生成的派生快照，同时作为后续普通 render 的受管来源保存。第一版中，`locks.outputs` 声明的全部路径固定归对应模板的 `overlays/<name>/static/` 所有，不支持写入 shared，也不依赖“当前路径所有者”推断归属。未来若要把持续完全一致的生成文件提升到 shared，必须另行确认并实现所有权迁移流程。

### 锁文件生成任务配置

不同语言的锁文件生成命令由 overlay 根部的 monorepo-only mise adapter 拥有，`templates.toml` 不直接保存原始 shell 命令。

语言工具版本仍由最终模板配置拥有：Go adapter 使用 `mise -C <template-root> exec -- go ...`，Rust adapter 使用 `mise -C <template-root> exec -- cargo ...`，从 staging 模板最终生成的 `mise.toml` 解析工具版本。overlay 根部不重复声明 Go 或 Rust。aube 是 monorepo 维护例外，三个 `overlays/<name>/mise.toml` 都声明 `aube = "1"`，用于统一维护 `docs/pnpm-lock.yaml`。

每个正式模板在 `templates.toml` 中只登记允许输出路径，例如：

```toml
[templates.go-cli.locks]
outputs = [
  "mise.lock",
  "mise.ci.lock",
  "go.mod",
  "go.sum",
  "tools/apply-existing/go.mod",
  "docs/pnpm-lock.yaml",
]
```

三个 overlay 根部的 monorepo-only adapter 统一暴露 `mise run locks:update [--bump] <template-root>`，在任务内部调用各自的原生命令。根工具为当前模板加载对应 overlay adapter，在临时完整模板中运行该任务，并验证任务没有修改 `outputs` 之外的路径；最终生成模板不包含该维护任务。

这种结构保持以下所有权：

- `templates.toml` 拥有允许变化的输出集合；固定的 `locks:update` 任务名属于 adapter interface。
- overlay 根部的 monorepo-only mise adapter 拥有 Go、Cargo、aube 和 mise 等具体命令及执行顺序。
- 原生包管理器拥有锁文件内容。
- 根工具拥有临时执行、变化验证、来源回写和最终 render 流程。

`outputs` 的来源所有权和存储位置已经确认：所有声明路径均回写到当前模板的 `overlays/<name>/static/`。

### 锁文件是否纳入版本管理

不建议忽略锁文件或只在检查中临时生成。当前模板行为依赖受版本管理的锁文件：

- 自动化检查设置 `MISE_LOCKED=1`，需要完整的 `mise.lock` 与 `mise.ci.lock`。
- Rust 的构建、检查和测试使用 Cargo `--locked`。
- 文档依赖安装使用 frozen lockfile 语义。
- Go 的 `go.sum` 提供模块内容校验，`go mod tidy -diff` 以已提交状态为基线。
- 模板目标要求生成项目完整、自包含且依赖解析可复现。

如果不提交锁文件，就必须移除或削弱上述合同；新项目首次运行还会立即产生一批未提交文件，模板快照也无法表达实际使用的依赖解析结果。

将原生生成文件回写到 `overlays/<name>/static` 并不违反 static 的语义：static 只表示 renderer 按字节复制、不解释内容；这些文件仍然是由原生命令生成的受管 render 输入。第一版不把任何 `locks.outputs` 路径写入 shared。

已确认把 monorepo 专属的锁文件命令组放在 overlay 根部，而不是放进最终模板：

```text
overlays/common/mise.toml
overlays/go-cli/mise.toml
overlays/rust/mise.toml
```

这些文件不是 `overlays/<name>/static/mise.toml`，renderer 不会把它们输出到模板。它们只为 monorepo 根工具提供语言 adapter，例如统一任务名：

```text
mise run locks:update [--bump] <template-root>
```

根工具以 `overlays/<name>` 为工作目录启动 adapter，并设置：

```text
MISE_CEILING_PATHS=<monorepo-root>
MISE_GLOBAL_CONFIG_FILE=/dev/null
MISE_TRUSTED_CONFIG_PATHS=<overlay-root>:<staging-template-root>
```

ceiling 排除 monorepo 根配置，`/dev/null` 排除用户全局配置，临时 trusted paths 同时允许加载 overlay adapter 和 staging 模板配置。调用不使用 `MISE_CONFIG_FILE`，不执行 `mise trust`，不修改用户持久信任状态；其他调用者环境正常继承。

根工具不覆盖 `MISE_AUTO_INSTALL`、`MISE_TASK_RUN_AUTO_INSTALL`、`MISE_EXEC_AUTO_INSTALL` 或 `MISE_OFFLINE`。默认情况下 mise 自动准备声明工具；调用者显式限制自动安装或网络时保持其策略，缺少工具或缓存则直接失败。adapter 不回退到系统 Go、Cargo、pnpm 或其他未声明工具。

已确认流程如下：

1. 根工具读取 `[templates.<name>.locks]` 的输出清单。
2. staging render 生成完整模板，并保留当前已提交的 `locks.outputs` 文件作为原生命令输入；首次尚不存在的允许输出可以在 adapter 执行前缺失。
3. 根工具从 `overlays/<name>/mise.toml` 加载 monorepo 专属 adapter，并把 staging 模板根目录作为必填位置参数、把根任务收到的可选 `--bump` flag 透传给 overlay `locks:update`。
4. overlay 任务默认在 staging 模板中运行一次 `mise -E ci lock`，由 mise 同时更新 `mise.lock` 与 `mise.ci.lock`；收到 `--bump` 时运行 `mise -E ci lock --bump`。随后运行 Go、Cargo 等模板专属原生命令，并统一运行 `aube install --lockfile-only -C <template-root>/docs` 更新 `docs/pnpm-lock.yaml`；不额外运行 `mise lock`，也不创建文档 `node_modules`。
5. 根工具复用 renderer 的文件树扫描比较任务前后的 staging 状态，只允许清单中的路径变化；adapter 成功后，每个声明路径都必须存在于 staging 根目录内并且是普通、不可执行文件，拒绝目录和 symlink。
6. 根工具把这些完整生成文件写回 `overlays/<name>/static/<path>`，然后执行普通 render 生成最终模板快照。
7. 普通 `render` 和 `sync:check` 不运行原生命令；现有模板检查继续消费已提交的锁文件。

正式回写具有失败回滚语义。根工具先复制完整的 `overlays/<name>/static` 到临时同级目录，只在副本中替换声明输出，再通过目录 rename 与备份切换正式来源并 render 模板；adapter、输出验证、回写、render、`sync:check` 或模板完整检查任一阶段失败时，恢复调用前的 overlay 与模板目录。全部验证成功后才删除备份。该合同覆盖正常错误和可处理的中断，不承诺抵抗 `SIGKILL` 或系统崩溃的跨目录原子性。

`templates.toml` 只保存输出清单，因为根工具必须知道哪些路径可以从 staging 回写；固定的 `locks:update` 任务名不进入配置。命令实现和执行顺序由 overlay 根部的 `mise.toml` 拥有，根工具直接依赖统一 adapter interface。

锁文件原生命令有时会同时规范化依赖清单，例如 Go 的 `go mod tidy` 可能修改 `go.mod` 和 `go.sum`，因此清单表示完整的允许回写路径集合，而不局限于文件名包含 `lock` 的文件。

三个模板的 monorepo-only adapter 都使用 aube 更新文档依赖锁文件。aube 直接读写现有的 `docs/pnpm-lock.yaml`；Go 模板生成后的普通 `docs:*` 任务本轮仍保持使用 pnpm，不随 monorepo 维护 adapter 一同迁移。

Go adapter 依次运行 `mise -C <template-root> exec -- go -C <template-root> mod tidy` 和 `mise -C <template-root> exec -- go -C <template-root>/tools/apply-existing mod tidy`，从 staging 模板配置解析 Go 版本，不运行 `go get -u`。根级 `--bump` 第一版只传给 mise 锁文件命令，不改变 Go module 版本。当前嵌套 module 只使用标准库，因此允许输出包含其现有的 `tools/apply-existing/go.mod`，但不包含尚不存在的 `tools/apply-existing/go.sum`；未来 tidy 产生该文件时，未声明输出检查必须失败并要求更新合同。

Rust adapter 运行 `mise -C <template-root> exec -- cargo generate-lockfile --manifest-path <template-root>/Cargo.toml`，从 staging 模板配置解析 Rust/Cargo 版本，不运行 `cargo update`。允许输出为 `mise.lock`、`mise.ci.lock`、`Cargo.lock` 和 `docs/pnpm-lock.yaml`，不包含不应被该命令修改的 `Cargo.toml`。根级 `--bump` 第一版只影响 mise 锁文件命令，不切换 Cargo 行为。

common adapter 不运行 placeholder `deps:fix` 或 `deps:update`，只运行 mise 锁文件命令和 aube 文档锁文件命令。允许输出为 `mise.lock`、`mise.ci.lock` 和 `docs/pnpm-lock.yaml`，不为尚不存在的语言依赖状态预留输出路径。

### 三层检查边界

锁文件更新和检查分属三个不同的 seam，不互相调用：

1. **模板项目检查**：最终生成的 `templates/<name>/mise run check` 只消费已提交的锁文件，验证项目在 locked/frozen 状态下能够工作；它不能读取 overlay 根部的 monorepo-only `mise.toml`，也不负责重新生成锁文件。
2. **快照同步检查**：根级 `sync:check` 只验证 shared、overlay 来源和 `templates/<name>` 快照一致，不运行语言依赖更新命令。
3. **更新流程验证**：monorepo 根工具在 staging 模板中调用 `overlays/<name>/mise.toml` 的 `locks:update`，验证生成命令成功、只修改声明路径，并负责回写；这属于 monorepo 维护工具的集成测试，不属于最终模板的 `mise run check`。

模板项目的普通 `mise run check` 不跨环境验证 `mise.ci.toml`，也不提供 `ci:tools:check` 或 `locks:check` 任务。GitHub Actions workflow 直接执行 `mise -E ci install --dry-run --locked`，验证基础与 CI 环境对应的两套 mise 锁文件；这是 workflow 的环境准备特例，不是项目检查任务。Go 的 `tidy -diff`、Cargo `--locked` 和 aube frozen lockfile 仍属于模板项目自身的只读消费检查。

monorepo 不额外暴露真实锁文件生成 smoke-test task，也不在普通 pull request 检查中执行一遍不回写的 `locks:update`。根工具使用受控 fixture 集成测试验证 staging、允许输出、越界修改拒绝、来源回写和最终 render；真实原生命令只由维护者主动执行的 `locks:update`、依赖更新或 release 演练触发。

越界修改检测直接复用 renderer 的文件树快照，比较相对路径、普通文件或 symlink 类型、可执行位、文件字节和 symlink 目标，不比较 mtime、目录权限和其他 Git 不跟踪的元数据，也不初始化临时 Git 仓库。任何不在 `locks.outputs` 中的变化都失败，包括 `.gitignore` 命中的缓存或 `node_modules`；选定的原生命令不得在 staging 中创建这些路径。

允许输出验证只检查边界属性：路径必须留在 staging 根目录内，最终存在，并且是普通、不可执行文件。根工具拒绝目录和 symlink，但不解析 mise、Go、Cargo 或 pnpm 锁文件格式，也不强制文件非空；内容合法性由原生工具和后续 locked/frozen 检查负责。

## 后续讨论队列

mise、adapter 和锁文件流程的前置决策已经确认。接下来逐项讨论模板 workflow，每次只确认一个决策：

1. `ci.yml` 必须保留的触发器、job 拓扑、缓存和审计差异。
2. `ci.yml` 共享 layout 的语义 slot。

## 现状验证记录

- `mise run sync:check` 已确认 common、Go 和 Rust 生成快照均处于同步状态。
- template-tool 的 14 个单元与本地 Git 集成测试通过，其中 10 个覆盖 renderer/锁更新，4 个覆盖首次 apply、保护路径、冲突现场、取消和单父提交历史。
- 三个模板的本地 `mise run check` 均已验证通过。
- 三个模板的真实 `locks:update` 均已执行成功；common 与 Rust 原生重生成后字节不变，Go 的 `git-cliff` 锁条目从基础 `mise.lock` 迁移到 `mise.ci.lock`。
- Rust 模板完整检查耗时约 111 秒，后续本地和 CI 超时设置需要覆盖该时长。
- 根级 `check-templates` 在进程被强制终止时可能遗留临时的 `templates/<name>/.git` 标记；在依赖该任务建设外层 CI 前需要修复中断清理行为。

## 决策记录

| 编号 | 决策 | 状态 |
| --- | --- | --- |
| D1 | `mise.ci.toml` 表示可本地运行的自动化与维护环境 | 已确认 |
| D2 | 三个模板统一使用 `mise -E ci run audit` | 已确认 |
| D3 | 普通 `mise.toml` 保留离线 `actions:check`，`mise.ci.toml` 提供在线 `actions:versions:check` | 已确认 |
| D4 | shared `mise.ci.toml` 使用 `maintenance_tools`、`audit_tasks`、`release_version_tasks` 和 `release_package` 四个 slot | 已确认 |
| D5 | shared 完整拥有五个公共 release helper，首次收敛只迁移所有权、不改变行为 | 已确认 |
| D6 | common placeholder 成功退出，真实 adapter 直接传播失败，Go 审计串行 fail fast | 已确认 |
| D7 | 锁文件由完整模板配置生成，普通 render 不运行原生锁文件命令 | 已确认 |
| D8 | `templates.toml` 只配置允许输出；固定的 `locks:update` 任务名和语言命令都不进入模板 profile | 已确认 |
| D9 | 第一版所有 `locks.outputs` 固定回写 `overlays/<name>/static`，不写入 shared；`generated/` 方案撤销 | 已确认 |
| D10 | `generated/` 第一版只允许保存锁文件生成结果 | 已撤销 |
| D11 | 模板 `locks:update` 注册在普通 `mise.toml` | 已撤销 |
| D12 | `locks.outputs` 表示允许更新的完整依赖状态路径集合，可包含 manifest | 已确认 |
| D13 | 模板项目 `mise run check` 只消费已提交锁文件，不调用 monorepo 的 `locks:update` | 已确认 |
| D18 | 不额外暴露真实锁文件生成 smoke-test task，也不纳入普通 PR 检查；真实生成由主动维护流程触发 | 已确认 |
| D14 | overlay 根部的 monorepo-only `mise.toml` 提供 `locks:update` 命令组 | 已确认 |
| D15 | overlay `locks:update` 接收一个模板根目录位置参数和可选 `--bump` flag，并只修改该 staging 目录 | 已确认 |
| D16 | shared `mise.ci.toml` layout 的四个 slot 采用固定 TOML 落点 | 已确认 |
| D17 | 普通 `check` 不跨环境验证 CI 工具，不新增 `ci:tools:check` 或 `locks:check`；workflow 直接调用 mise CLI 验证 CI 环境锁文件 | 已确认 |
| D19 | overlay 锁文件 adapter 只运行一次 `mise -E ci lock`，同时生成 `mise.lock` 与 `mise.ci.lock` | 已确认 |
| D20 | `locks:update` 默认保留已有 mise 版本解析；显式 `--bump` 时才重新解析模糊工具选择器 | 已确认 |
| D21 | 三个 overlay adapter 统一使用 `aube install --lockfile-only` 更新 `docs/pnpm-lock.yaml`，不改变 Go 模板的日常 pnpm 任务 | 已确认 |
| D22 | Go adapter 对根 module 和 `tools/apply-existing` 运行 `go mod tidy`，不主动升级依赖；输出清单暂不包含不存在的嵌套 `go.sum` | 已确认 |
| D23 | Rust adapter 使用 `cargo generate-lockfile`，不使用 `cargo update`，允许输出不包含 `Cargo.toml` | 已确认 |
| D24 | common adapter 只维护 mise 与文档锁文件，不调用 placeholder 项目依赖任务 | 已确认 |
| D25 | staging 保留已有依赖状态文件；首次允许输出可在执行前缺失，但 adapter 成功后必须全部存在 | 已确认 |
| D26 | 越界修改检测复用 renderer 文件树快照，不创建临时 Git 仓库，也不忽略任何未声明路径 | 已确认 |
| D27 | `locks.outputs` 最终必须是 staging 内的普通、不可执行文件；拒绝目录和 symlink，不自研内容解析 | 已确认 |
| D28 | `locks:update` 任一阶段失败时恢复调用前的 overlay 与模板目录；成功完成全部验证后才提交更新 | 已确认 |
| D29 | adapter 使用 ceiling、禁用全局配置和进程级双路径临时信任，不修改用户 mise trust 状态 | 已确认 |
| D30 | Go 与 Cargo 从 staging 模板 mise 配置解析；overlay 不重复语言版本，只声明 monorepo 维护用的 `aube = "1"` | 已确认 |
| D31 | `locks:update` 尊重调用者的 mise auto-install 与 offline 设置，缺工具时失败，不回退到未声明系统工具 | 已确认 |
| D32 | 删除冗余的 `locks.task` 配置；根工具直接依赖统一的 overlay adapter interface | 已确认 |
