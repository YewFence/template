# 模板 Monorepo 初步计划

## 背景

当前工作区包含三个彼此独立的 Git 仓库：

- `common-template`：语言无关的工程模板
- `go-cli-template`：Go CLI 工程模板
- `rust-template`：Rust 工程模板

三个模板共享大量工程行为，包括 mise 任务、Git hooks、文档站点、GitHub Actions、依赖更新、版本计算和发布流程。当前这些行为以复制后的完整文件存在于各仓库中，语言适配和通用实现也经常位于同一文件，因此修改需要人工同步，容易产生无意漂移。

## 目标

1. 使用一个 monorepo 作为三个模板及其共享行为的唯一事实来源。
2. 共享行为只维护一份，修改后能够一致地作用于所有适用模板。
3. 每个模板继续保有完整、可直接使用的目录内容，包括自包含的 Renovate、mise 和 GitHub Actions 配置；生成后的项目不在运行时依赖本 monorepo 的共享来源。
4. 使用稳定的 mise 任务接口隔离语言无关行为和语言特有行为。
5. 在 CI 中自动发现共享内容未同步、生成结果过期或模板行为不一致等问题。
6. 保留各模板独立测试、构建和发布的能力。

## 非目标

- 第一阶段不引入 Josh、Git submodule 或 Git subtree。
- 第一阶段不要求继续维护三个独立远端仓库。
- 不把三个语言模板强行统一成完全相同的文件结构。
- 不把普通项目生成后的源码变成对 monorepo 共享目录的运行时依赖。
- 不在迁移过程中顺带重写所有现有 CI 和发布流程。

## 设计原则

### 唯一事实来源

共享行为必须存在于明确的共享模块中。模板目录里的派生文件如果仍需提交，必须能够由共享来源重新生成，并由 CI 验证生成结果没有过期。

### 稳定接口

各模板通过统一的 mise 任务接口暴露常见能力：

- `deps:check`
- `deps:fix`
- `deps:update`
- `fmt:check`
- `fmt:fix`
- `lint`
- `build`
- `build:check`
- `test`
- `audit`（通过 `mise -E ci run audit` 暴露）
- `release:package`

共享模块负责组合这些任务，并提供 `check`、`fix`、`actions:*`、`docs:*`、`release:*` 等语言无关行为。Go、Rust 和语言无关模板分别提供自己的 adapter，实现确实会随模板变化的任务。
基础 `mise run check` 不隐式执行安全审计；审计属于 `mise.ci.toml` 提供的自动化与维护接口，避免日常检查依赖额外工具或在线漏洞数据。

### 薄 CI

GitHub Actions workflow 应尽量只负责权限、触发条件、缓存和调用稳定的 mise 任务。可复用的项目检查决策和命令应放在 mise 任务或脚本中，避免相同业务逻辑散落在多个 workflow 文件里。mise 环境选择、工具安装和锁文件完整性属于 workflow 启动自身的基础设施，可以作为特例直接调用 mise CLI，不需要包装成项目任务。

monorepo 根目录的 `.github/workflows/` 属于维护仓库自身基础设施，直接维护且不参与模板 render；它调用根级 mise tasks 和 Python 工具，验证渲染、三个模板和应用器。只有 `shared/` 与 overlay 中用于最终模板的 workflow 会生成到 `templates/<name>/.github/workflows/`。根 workflow 不从 shared 生成，避免形成生成器 CI 依赖生成器输出的循环。

### 可验证生成

共享内容的同步不能依赖维护者记忆。根级任务应支持重新生成模板，并提供只读检查，用于确认工作树中的派生文件与共享来源一致。

### 双层结构

共享来源位于 `shared/`，三个模板目录中的对应文件是提交到 monorepo 的生成快照。模板快照必须保持完整、可独立使用，不能依赖 monorepo 中的 `shared/` 或根级 mise 配置；CI 通过 `sync:check` 阻止共享来源与快照不一致。

### Layout、Slot、Fragment 与 Overlay

模板采用“共享静态来源 + 同名 layout + named slot + 可复用 fragment + 模板 overlay”模型。layout 定义路径特有的完整文件骨架和稳定的 slot interface；fragment 实现某个 slot；`templates.toml` 中的正式模板 profile 只负责把 fragment 显式绑定到自动发现 layout 的 slot。跨文件和跨模板复用集中在 fragment 层，不为复用几行骨架引入 layout 实例化或输出映射。

迁移首轮不要求立刻实现上述全部抽象。三个现有仓库各自的 tracked Git tree 是对应模板的权威来源：已经确认字节和 Git mode 一致的文件可以进入 `shared/static/`，其余文件无论差异大小都先完整进入对应 `overlays/<name>/static/`。首轮生成不得改变现有行为或文件内容；只有后续逐项确认共同合同后，才把全文件 overlay 提升为 shared layout、slot 和 fragment。workflow、mise、Renovate 等文件的行为择优与 slot 收敛不阻塞 monorepo 基线重构。

完全一致且不需要参数化的文件位于 `shared/static/`，按原样复制。`shared/layouts/` 和 `shared/fragments/` 只允许保存不假设具体模板、语言、工具链或发布形态的共享逻辑。任何明确知道自己属于 common、Go、Rust 或某个特定模板的静态文件、layout 和 fragment 都必须位于 `overlays/<name>/`；只有出现真实的跨模板共享合同后，才能提升到 `shared/`。

slot 必须按行为语义命名，例如 `repository_tasks`、`project_tasks`、`cache_setup` 和 `release_assets`，不得按文件位置命名为 `before_step_2` 或 `extra_yaml`。普通 slot 至少绑定一个 fragment，声明 `optional=true` 的 slot 允许不绑定；所有 slot 都允许按配置顺序绑定多个 fragment，不引入额外 cardinality 枚举。fragment 不拥有输出路径、不读取当前 profile 名称或整个 `templates.toml`。第一版禁止多层模板继承和 fragment 循环引用，只允许一层 layout 加显式 fragment。

layout 和 fragment 使用 Jinja2 渲染，但不使用默认的双花括号语法。现有模板需要原样保留项目初始化占位符、GitHub Actions 表达式、mise Tera 和 git-cliff Tera，因此 monorepo renderer 固定使用以下分隔符：变量和 slot 为 `<$ ... $>`，控制块为 `<% ... %>`，注释为 `<# ... #>`。Jinja2 环境使用 `StrictUndefined`、关闭 autoescape、保留末尾换行并固定输出换行为 `\n`。

layout 不允许使用 Jinja2 `extends`，也不允许根据 `template_name`、profile 名称或等价隐式全局变量选择 Go、Rust、common 等实现。模板差异只能通过显式 slot binding 进入，第一版不提供 output-scoped 或 fragment-scoped context。Jinja2 只处理 `layouts/` 与 `fragments/`；`static/` 永远按字节复制。模板源码属于受信任的 monorepo 输入，应用器不接受用户提供任意 Jinja2 源码。loader 只允许读取当前声明的 shared 或 overlay 来源根，拒绝绝对路径和经过归一化后越界的 `../`。

原生 include、reusable workflow、composite action 和其他工具自带 composition 能力仍可使用，但只在它们能改善最终生成项目自身的维护性时采用，不再作为 monorepo 共享的必要前提。Renovate 等不支持本地拆分配置的工具由生成器直接物化完整配置。

生成器按输出路径自动归并 shared 与当前 overlay 的来源集合，但不实现通用 YAML、TOML、JSON 深层合并，也不对缺少共同祖先的输入调用 Git 内容合并。某个输出路径只在一侧存在时默认直接采用该来源，除非该模板以 `omit` 显式省略；shared 与 overlay 都提供同一输出路径时，必须通过 `templates.toml` 的精确路径规则选择 `shared`、`overlay` 或 `omit`。同一侧的 static 与 layout 输出冲突、未声明的跨侧路径冲突、slot 未填、绑定未知 slot、slot 重复声明、普通顶层 key 重复归属或无法确定输出时，render 必须失败。每个结构化共享模块仍需定义有限、明确的所有权和组合规则；路径规则只处理整文件来源选择和省略，不执行文件内容合并。

### 纯重建

`templates/<name>` 是完全可丢弃的生成输出，不是第三个来源。每次 `render` 都从 `shared/`、对应的 `overlays/<name>/` 和 `templates.toml` 重新构建完整目录；生成器不读取旧模板内容、不维护 render state、不分析文件依赖，也不试图判断生成结果的业务语义。实现上应先在临时目录完成生成和自动校验，成功后再整体替换目标目录，避免失败时留下半成品。相同输入必须产生相同输出，删除或重命名来源文件必须自然反映到输出目录。

## 初步目录结构

```text
template/
├── mise.toml
├── templates.toml
├── MONOREPO_PLAN.md
├── renovate.json
├── config/
│   └── renovate/
│       └── monorepo.json
├── shared/
│   ├── static/
│   ├── layouts/
│   ├── fragments/
│   ├── renovate/
│   │   └── base.json
├── overlays/
│   ├── common/
│   │   ├── static/
│   │   ├── layouts/
│   │   └── fragments/
│   │       └── renovate/profile.json
│   ├── go-cli/
│   │   ├── static/
│   │   ├── layouts/
│   │   └── fragments/
│   │       └── renovate/profile.json
│   └── rust/
│       ├── static/
│       ├── layouts/
│       └── fragments/
│           └── renovate/profile.json
├── templates/
│   ├── common/
│   ├── go-cli/
│   └── rust/
├── tools/
│   └── template-tool/
│       ├── pyproject.toml
│       └── src/template_tool/
│           ├── apply.py
│           ├── render.py
│           └── git.py
└── scripts/
    └── apply-template
```

这是第一版的固定目录合同：`shared/static/`、`shared/layouts/` 和 `shared/fragments/` 是模板无关的共享来源；`overlays/<name>/static/`、`overlays/<name>/layouts/` 和 `overlays/<name>/fragments/` 是模板专属来源；`templates/<name>/<path>` 是最终生成快照。layout 按相对路径自动发现，移除 `layouts/` 前缀和末尾 `.j2` 后的路径就是输出路径，例如 `shared/layouts/.github/workflows/ci.yml.j2` 生成 `.github/workflows/ci.yml`。`templates.<name>` 的配置名必须同时对应对应的 overlay 和输出目录。迁移时应优先保持现有模板路径和文件内容稳定。

`shared/` 和 `overlays/` 共同构成 render 的唯一编辑来源，`templates/common`、`templates/go-cli` 和 `templates/rust` 中的生成文件不作为第二个来源维护。生成结果保留在 Git 中，便于审查模板的实际变化和独立发布。根目录中由共享模块生成的文件，例如 `renovate.json`，也必须由 `sync:check` 验证。

模板 overlay 位于 `overlays/common`、`overlays/go-cli` 和 `overlays/rust`，只记录对应模板的有意差异。绑定使用显式的 `shared:` 或 `overlay:` 来源命名空间，分别相对 `shared/fragments/` 和当前模板的 `overlays/<name>/fragments/` 解析；同一个 fragment 可以绑定到多个 slot 或多个 layout，但 overlay 来源不能被其他模板隐式引用。生成器不允许通过绝对路径或 `../` 绕过所有权目录。

`templates.toml` 是 `render-template` 和 `apply-template` 共享的唯一配置合同，登记正式模板名称、按输出路径分组的 named-slot bindings、整文件省略或跨侧同名输出选择的显式路径规则，以及 `[apply]` 的保护路径和 HINT；不登记 layout 路径或 context。生成器自动发现 shared 和当前 overlay 的来源并按输出路径取并集，不要求配置维护所有静态文件的完整清单。只在一侧存在的路径默认直接采用，也可显式 `omit`；两侧重复的路径必须显式选择来源或省略。未知 slot、必填 slot 缺失、slot 重复声明、同一侧输出冲突和未声明的跨侧冲突都必须失败。

第一版 binding 结构保持简单，输出路径直接作为 `slots` 下的 quoted key，所有 fragment 绑定都使用数组，不提供单字符串简写：

```toml
[templates.go-cli]

[templates.go-cli.paths]
".github/workflows/ci.yml" = "overlay"
"docs/internal.md" = "omit"
"LICENSE" = "shared"

[templates.go-cli.slots."mise.toml"]
repository_tools = [
  "shared:mise/repository-tools.toml.j2",
]
project_tools = [
  "overlay:mise/project-tools.toml.j2",
]
repository_tasks = [
  "shared:mise/repository-tasks.toml.j2",
]
project_tasks = [
  "overlay:mise/project-tasks.toml.j2",
]
release_tasks = [
  "shared:mise/release-metadata.toml.j2",
  "overlay:mise/release-package.toml.j2",
]
```

`paths` 的 key 是最终输出中的精确相对路径，value 只能是 `shared`、`overlay` 或 `omit`。它不支持 glob、目录规则、重命名或输出映射，也不作为完整文件清单使用：`shared` 和 `overlay` 只用于解决两侧都映射到该输出路径的真实冲突，选择其中一侧的整文件来源；`omit` 可以省略单侧或双侧存在的路径。对单侧路径声明 `shared` 或 `overlay` 属于冗余配置，规则指向两侧都不存在的路径属于失效配置，二者都必须失败；同一侧同时有 static 和 layout 映射到该路径，或跨侧重复但没有路径规则时同样失败。若选中 layout，仍按该输出路径执行正常的 slot binding。

对应 layout 使用 `<$ slot("repository_tasks") $>` 声明必填 slot，使用 `<$ slot("release_tasks", optional=true) $>` 声明 optional slot。fragment 按数组顺序渲染和拼接；同一个 fragment 可以在多个 binding 中复用。第一版不支持同一个 layout 实例化到多个输出路径，需要跨文件复用时提取共享 fragment，并保留薄的同名 layout。

Renovate 规则由 `shared/renovate/base.json`、`config/renovate/monorepo.json` 和各 `overlays/<name>/fragments/renovate/profile.json` 生成完整配置。`base.json` 独占公共顶层策略；模板专属 profile 主要提供 manager 专属设置和 `packageRules`；monorepo profile 独占根仓库扫描范围、manager 并集和 `ignorePaths`。`packageRules` 按声明顺序拼接，普通顶层 key 不允许在 base 与 profile 之间重复归属，不实现 Renovate 任意配置的自有深层合并算法。

根目录 `renovate.json` 由 base 与 monorepo profile 生成，只扫描和修改根工具、`shared/**` 与 `overlays/**` 中的真实来源，并明确忽略 `templates/**`。每个模板的 `renovate.json` 由 base 与自己的 profile 生成完整、自包含的配置，不引用 `github>`、`local>` 或本 monorepo 的远程 preset。

中央 Renovate 规则修改不会自动传播到已经生成的外部项目。`v0.1.0` 不提供受支持的模板升级或重复 apply 合同；外部项目只能人工参考新模板 diff 选择性移植规则，或等待未来另行设计的正式升级协议。这是模板快照自包含和可复现性的明确取舍，不再维护第二条远程 preset 分发通道。

正式模板必须通过 `[templates.<name>]` 显式声明，不自动扫描 `overlays/*` 发现。每个声明都必须存在同名 overlay；未声明的 overlay 目录、未声明的模板输出目录和 `apply-template` 请求的未知模板都必须失败。`templates/<name>` 可以在首次 render 前不存在，由生成器创建。

`render-template` 支持指定一个已声明模板或使用 `--all` 处理全部正式模板，并支持 `--check` 只读比较模式；不接受任意模板列表。`apply-template` 每次必须且只能通过 `--template` 选择一个模板，不能批量应用。根级 mise 可以直接包装 `render-template --all` 和 `render-template --check --all`。

`render-template --check` 按 Git tree 语义比较期望输出与已提交快照，包括路径集合、文件字节内容、executable bit、符号链接目标以及新增和删除结果；不比较 mtime、目录权限和其他 Git 不跟踪的文件系统元数据。发现不一致时返回非零，先列出路径再打印 Git 风格 diff。`--check --all` 应检查完所有模板后汇总失败模板，不在第一个差异处提前停止。

render 阶段直接验证输出 symlink：拒绝绝对 symlink，以及路径归一化后逃出对应 `templates/<name>` 根目录的相对 symlink。符号链接安全属于生成器的确定性输入验证，不依赖导出环境测试。

生成快照路径禁止直接编辑。共享行为和模板专属内容都必须回到 `shared/` 下的共享来源、对应的结构化共享模块或 `overlays/<name>/` 修改，再通过 `render` 更新快照；语言工具链、依赖元数据、源码、语言测试和打包脚本等模板专属内容同样由 overlay 维护。`sync:check` 必须能报告直接修改生成快照造成的不一致，并指出对应的静态来源、layout、fragment 或 binding。

### 锁文件

锁文件和其他由原生命令规范化的依赖状态文件是受管 render 输入，绝不手工编辑。第一版中，每个模板在 `locks.outputs` 声明的全部路径固定归对应的 `overlays/<name>/static/` 所有，不支持写入 shared，也不根据路径当前是否存在或当前位于哪一侧来推断所有权。未来如果证明某个生成文件在所有适用模板中持续完全一致，再单独设计并确认将其提升到 shared 的所有权迁移流程。

根级 `locks:update [--bump] <template>` 在临时目录 render 完整模板，并保留当前已提交的全部依赖状态文件作为原生命令输入；首次尚不存在的允许输出可以在 adapter 执行前缺失，但成功后必须全部存在。根工具调用 mise、Cargo、Go、aube 或其他原生命令更新依赖状态，只允许 `locks.outputs` 中的路径发生变化，再把所有声明输出回写到对应的 `overlays/<name>/static/<path>`，最后重新 render 并执行 `--check`。mise 锁文件默认只运行一次 `mise -E ci lock`，由 mise 原生同时更新基础 `mise.lock` 与环境专属 `mise.ci.lock`，不再额外运行 `mise lock`；显式传入 `--bump` 时改为运行 `mise -E ci lock --bump`，重新解析模糊工具选择器。三个模板的文档依赖统一由 monorepo-only adapter 执行 `aube install --lockfile-only -C <template-root>/docs`，继续生成兼容的 `docs/pnpm-lock.yaml`，不创建 `node_modules`；本轮不改变 Go 模板生成后的普通 pnpm 任务。直接在 `templates/<name>` 中产生的锁文件变化不能提交。

`locks:update` 具有失败回滚语义：overlay adapter、输出边界验证、来源回写、render、`sync:check` 或模板完整检查任一阶段失败时，正式的 `overlays/<name>/static` 与 `templates/<name>` 都必须保持调用前状态。根工具先在 staging 完成原生命令与验证，再复制完整 overlay static 到临时同级目录并替换声明输出，通过目录 rename 与备份切换正式来源；后续失败时恢复原 overlay 和原模板，全部验证成功后才删除备份。该合同覆盖正常错误和可处理的中断，不声称在进程被 `SIGKILL` 或系统崩溃时提供跨目录原子事务。

根工具从 `overlays/<name>` 启动 monorepo-only adapter，并为子进程设置 `MISE_CEILING_PATHS=<monorepo-root>`、`MISE_GLOBAL_CONFIG_FILE=/dev/null` 和由 overlay 根目录、staging 模板根目录组成的 `MISE_TRUSTED_CONFIG_PATHS`。这样 adapter 不加载 monorepo 根配置或用户全局配置，内部 `mise -E ci lock` 又能读取受信任的 staging 配置。调用不使用 `MISE_CONFIG_FILE`，不执行 `mise trust`，不修改用户持久信任状态；`PATH`、代理、凭据和 `MISE_OFFLINE` 等其他调用者环境正常继承。

根工具不强制设置 `MISE_AUTO_INSTALL`、`MISE_TASK_RUN_AUTO_INSTALL`、`MISE_EXEC_AUTO_INSTALL` 或 `MISE_OFFLINE`。没有调用者覆盖时，mise 按默认行为自动安装 overlay 声明的 aube 和 staging 声明的 Go/Rust；调用者显式禁用自动安装或启用离线模式时保持其选择，缺少必要工具或缓存则直接失败，不回退到未声明的系统 Go、Cargo、pnpm 或其他工具。

Go 和 Cargo 的可执行版本由 staging 模板最终生成的 `mise.toml` 拥有，overlay 不重复声明语言版本。Go adapter 通过 `mise -C <template-root> exec -- go ...` 执行两个 module 的 tidy，Rust adapter 通过 `mise -C <template-root> exec -- cargo generate-lockfile ...` 生成锁文件。aube 是 monorepo 维护例外：三个 `overlays/<name>/mise.toml` 都声明 `aube = "1"`，由 overlay adapter 直接调用，不依赖 Go 模板当前仍使用 pnpm 的最终配置。

Go adapter 依次对模板根 module 和 `tools/apply-existing` module 执行 `go mod tidy`，只规范化当前 manifest、源码依赖图和校验文件，不运行 `go get -u`。根级 `--bump` 第一版只控制 mise 的模糊工具选择器，不升级 Go module 版本；Go 依赖升级仍由 Renovate 或生成模板已有的 `deps:update` 工作流负责。Go 的允许输出为 `mise.lock`、`mise.ci.lock`、`go.mod`、`go.sum`、`tools/apply-existing/go.mod` 和 `docs/pnpm-lock.yaml`；当前不存在的 `tools/apply-existing/go.sum` 不预先声明，未来该模块引入外部依赖时必须显式扩展输出合同。

Rust adapter 执行 `cargo generate-lockfile --manifest-path <template-root>/Cargo.toml`，根据当前 manifest 生成 `Cargo.lock`，不运行 `cargo update`，也不允许修改 `Cargo.toml`。根级 `--bump` 第一版不改变 Cargo 命令。Rust 的允许输出为 `mise.lock`、`mise.ci.lock`、`Cargo.lock` 和 `docs/pnpm-lock.yaml`。

common adapter 不调用 placeholder `deps:fix` 或 `deps:update`，只运行 mise 锁文件命令和 `aube install --lockfile-only -C <template-root>/docs`。common 的允许输出为 `mise.lock`、`mise.ci.lock` 和 `docs/pnpm-lock.yaml`，不为尚不存在的语言依赖文件预留路径。

`templates.toml` 的 `[templates.<name>.locks]` 只登记 `outputs`；固定的 `locks:update` 任务名属于 overlay adapter interface，不作为可配置字段。

第一版不额外暴露真实运行原生生成命令的锁文件 smoke-test task，也不在普通 pull request 检查中重复执行一遍不回写的 `locks:update`。根工具在 adapter 执行前后复用 renderer 的文件树扫描，对比相对路径、文件或 symlink 类型、可执行位、文件字节和 symlink 目标；任何不在 `locks.outputs` 中的变化都失败，包括被 `.gitignore` 忽略的缓存路径，不比较 mtime、目录权限和其他 Git 不跟踪的元数据，也不为此初始化临时 Git 仓库。adapter 成功后，每个声明输出都必须存在于 staging 根目录内并且是普通、不可执行文件，拒绝目录和 symlink；根工具不自研内容格式解析，也不要求文件非空。受控 fixture 集成测试覆盖 staging、允许输出验证、越界修改拒绝、输出类型验证、来源回写和最终 render；真实 mise、Go、Cargo 和 aube 生成命令只在维护者主动执行 `locks:update`、依赖更新或 release 演练时运行。

## 根级 mise 职责

外层 `mise.toml` 是 monorepo 的操作入口，而不是模板项目自身配置的替代品。第一版提供以下稳定任务：

| 任务 | 职责 |
| --- | --- |
| `render [template]` | 从共享来源更新指定模板；省略参数时更新全部正式模板 |
| `sync:check [template]` | 只读检查指定模板；省略参数时检查全部正式模板 |
| `check [template]` | 执行指定模板的完整检查；省略参数时检查全部正式模板 |
| `locks:update [--bump] <template>` | 通过模板对应的原生命令更新锁文件；可选重新解析模糊 mise 工具版本 |
| `actions:update` | 统一更新并固定 GitHub Actions 引用 |

`render`、`sync:check` 和 `check` 的可选 `template` 参数只能是 `common`、`go-cli` 或 `rust`，省略时统一表示全部正式模板；`locks:update` 必须显式指定其中一个模板，不提供隐式批量更新，并支持可选布尔 flag `--bump`。参数和 flag 使用 mise Usage DSL 声明、校验并提供帮助和补全，不在 shell 中手工解析。复杂实现和全量模式的错误聚合放入 `tools/template-tool/` 的 Python package，mise 只登记稳定接口、参数和任务元数据。

模板检查直接在 `templates/<name>` 原目录运行，以复用 mise 全局工具缓存和模板目录中的 Cargo、Go、Node 等项目缓存。自动化调用模板自身任务时同时设置 `MISE_CEILING_PATHS=<monorepo-root>`、`MISE_GLOBAL_CONFIG_FILE=/dev/null`、`MISE_TASK_RUN_AUTO_INSTALL=false` 和空 `RUSTFLAGS`：前两者排除根级与用户全局 mise 配置，第三项禁止检查过程隐式安装工具，最后一项防止用户级 Cargo 配置注入本机专属 linker flags；这些设置不改变已经安装的工具和项目构建缓存。不使用 `MISE_CONFIG_FILE` 模拟单文件加载。用户手动进入模板目录运行任务时不强制禁用个人全局配置。

自动化模板检查设置 `MISE_LOCKED=1`，并在运行模板自身的 `mise run check` 前后用 Git 验证 tracked 工作树和 index 均未变化，从而落实 read-only 任务合同；被 `.gitignore` 忽略的缓存不属于失败条件。普通 `mise run check` 不跨环境验证 `mise.ci.toml`，也不新增 `ci:tools:check` 或 `locks:check` 任务；GitHub Actions workflow 直接执行 `mise -E ci install --dry-run --locked`，把 CI 环境和两套 mise 锁文件的完整性作为 workflow 基础设施前置检查。发布前直接运行根级 `mise run sync:check`、`mise run check` 和应用器集成测试，不设置独立导出或真实锁文件生成 smoke test。

## 共享内容分类

迁移前先把现有文件分为以下三类：

### 完全共享

内容在三个模板中应当完全一致。这类文件可以直接来自 `shared/static/`。第一批提取范围已经确定为：

- `LICENSE`
- `cliff.toml`
- `hk.pkl`
- `docs/pnpm-workspace.yaml`

当前三份 `docs/pnpm-lock.yaml` 虽然字节一致，但它是原生工具生成的锁文件，第一版仍分别归三个模板的 overlay 所有。未来即使 `locks:update` 证明三个模板上下文持续生成相同结果，也必须另行确认并实现所有权迁移流程，不能由当前更新任务自动提升到 shared。

### 共享骨架加模板参数

整体结构一致，但名称、工具、缓存、审计实现或发布资产不同，例如 mise、GitHub Actions、Renovate 和文档站点配置。它们的目标形态是通过中性 layout、named slots、共享或 overlay fragment 以及每输出 binding 生成完整文件，避免脆弱的字符串替换和通用深层合并。迁移首轮在行为合同尚未逐项确认前保留完整文件 overlay，不为追求文本共享提前改变任一模板；后续确认一个共同合同，就把对应路径从全文件 overlay 收敛到 layout 和 slot。缓存等模板专属实现最终仍必须留在对应 overlay。

### 模板专属

语言工具链、依赖元数据、源码、语言测试和打包脚本等内容由对应的 `overlays/<name>/` 独立维护，再生成到模板目录；它们不需要在 shared 中存在，但仍然属于 render 的输入。

## 迁移阶段

### 阶段一：建立 monorepo 基线

1. 在外层初始化新的 Git 仓库。
2. 将三个仓库的冻结基线迁移到 `templates/` 下，不直接复制带有未提交修改的工作目录。
3. 将 GitHub `YewFence/template` 设为唯一官方主远端，默认分支为 `main`，许可证为 MIT；Forgejo 最多作为可重建镜像，不承担官方分发合同。
4. 在切换前记录旧仓库来源指纹，并完成新 monorepo 的 render、检查、应用器和 release 验证。

monorepo 第一版使用干净的新历史，不把三个旧仓库的完整提交图和 tag 作为迁移前提。旧 GitHub `YewFence/go-cli-template` 在切换后保留为只读归档；旧 Forgejo 仓库允许重建，Rust 不额外创建历史归档远端。common 和 Rust 只在迁移记录中保存来源仓库、原远端或无远端说明、基线 commit SHA、Git tree SHA、迁移时间、工作树状态和对应的新路径，不额外制作 Git bundle。

首轮重构已在 `2026-08-04T18:40:20+08:00` 冻结以下权威基线；三份工作树和 index 均为干净状态：

| 模板 | 原远端 | 基线 commit | Git tree | 新路径 |
| --- | --- | --- | --- | --- |
| common | `ssh://git@git.yewfence.dev:222/yewfence/template.git` | `5df78568ae7837fe27bf1143413181cf48668b7f` | `809ebdda1a987b84a0d6b989e958861dfb87a381` | `templates/common` |
| go-cli | `https://github.com/YewFence/go-cli-template.git` | `c4533174864512886ec97acc00bd85ea28fc6cf4` | `368f88f261a5d6aa8999729de68b4c6df7d85173` | `templates/go-cli` |
| rust | 无远端 | `41de7babcfbf62e9b8df69c4687b09dcee7c7744` | `d0cd086b24ef5e062a1f00995237a96dcf02f665` | `templates/rust` |

monorepo 第一版采用统一版本号和统一 release：首个正式版本为 `v0.1.0`，后续一个 `vX.Y.Z` tag 代表三个模板及其共享行为的同一份可复现快照。单个模板没有独立 tag namespace；release notes 标注具体变化影响了哪些模板。tag 一旦公开不得移动或覆盖。只有未来出现独立消费、独立回滚或独立权限需求时，才重新评估路径感知的多版本策略。

迁移不设置双写期。旧仓库先冻结，新 monorepo `v0.1.0` 通过 `sync:check`、三个模板检查、应用器集成测试以及公开分发验证后立即成为唯一维护入口；旧 Go 仓库随即归档，旧仓库不再接收功能提交、Renovate 更新或 release。

### 模板分发与应用器

模板使用者不下载 release 归档，而是通过应用器从 monorepo 的指定 ref 获取并应用完整模板快照。Python 工具位于 monorepo 根目录的 `tools/template-tool/`，提供 `render-template` 和 `apply-template` 两个独立 entrypoint；Bash fallback launcher 位于 `scripts/apply-template`，它们都和模板内容一起版本控制。`apply-template` 的 `--repo` 默认使用官方 monorepo 地址但允许覆盖，`--ref` 决定要获取的 `templates/<name>` 快照版本，`--template` 决定目标模板且必须显式提供。`--ref` 默认使用 `main`，需要严格复现时显式传入 tag 或完整 commit SHA。

当前实现决策是以同一个 Python package 承担渲染与应用逻辑，共享模板约定、配置解析、Git 调用和临时目录处理，但通过两个 entrypoint 保持维护者接口与用户接口分离。使用 uv 的用户可以通过 `uvx --from git+<repo>@<ref>#subdirectory=tools/template-tool apply-template` 直接选择并运行指定 Git ref 的应用器；Bash launcher 只作为没有 uv 时的 fallback，不承载 apply policy 等业务逻辑。Python 实现优先考虑标准库，模板渲染明确使用 Jinja2；其他第三方依赖和模块拆分在实现阶段根据真实复杂度决定。Python 源文件不使用绑定 uv 的 shebang，依赖与锁文件通过 uv 原生命令维护，不手工编辑。

uv 入口是正式支持路径，负责从指定 Git ref 解析、安装并运行应用器及其依赖。Bash fallback 只做 best-effort：它获取应用器源码并尝试使用系统 Python 运行，不实现 venv、pip、锁文件解析或第三方依赖安装；如果某个应用器版本无法在当前系统 Python 环境中直接运行，launcher 必须清晰失败并提示改用 uv。README 明确说明 Bash fallback 不保证覆盖所有应用器版本。

第一版正式支持 Linux 和 macOS；Windows 只支持 WSL，不承诺原生 Windows。Python 实现避免无必要的 Linux 专用路径假设，但 symlink、executable bit、Bash fallback 和 Git worktree 行为只在正式支持平台验证。

应用器必须沿用安全的目标仓库语义：目标 Git 工作树默认要求干净，模板变更进入暂存区供审查，应用器不替用户提交；应用过程失败时不留下半成品。应用器 fetch 后必须解析并打印最终 commit SHA，便于记录 `Template-Commit` 来源；默认跟随 `main` 是便利性选择，不能被误解为不可变输入。

干净仓库要求覆盖 tracked 修改、staged 修改和普通 untracked 文件，等价于 `git status --porcelain --untracked-files=normal` 为空；被 `.gitignore` 忽略的缓存不阻止应用，但路径占用由 Git 自己拒绝。应用器不提供 `--force`、自动 stash 或自动清理，用户必须在运行前自行处理现有工作。

应用器支持 detached HEAD 和 colocated Jujutsu 仓库，但 `HEAD` 必须指向真实 commit，不能是尚无提交的 unborn branch；目标仓库也不能存在进行中的 merge、rebase、cherry-pick 或 revert。应用器只操作 Git index 和工作树，不移动 branch、不创建提交、不调用 `jj`；输出 HINT 提醒用户完成、解决或取消本次应用后再继续普通 `jj` 操作。

应用器启动时打印最终仓库、模板、ref 和解析后的 commit SHA。模板路径始终由 `--template` 和固定的 `templates/<name>` 布局推导，不接受独立模板目录 URL，避免应用器与 monorepo 目录约定脱节。

私有仓库和其他 Git 服务的认证完全交给 Git：`--repo` 接受 Git 支持的 HTTPS 或 SSH 地址，应用器使用用户现有的 credential helper、GitHub CLI credential、SSH agent 和 SSH 配置，不读取或记录 token，也不实现额外的 GitHub API 认证流程。认证失败、网络失败和 ref 不存在都直接失败并保留清晰错误。

应用器使用 Git 原生的浅层 sparse checkout 获取输入：临时仓库只检出应用器本身和目标 `templates/<name>` 路径，不下载或展开无关模板与文档内容。第一版不引入 GitHub API、release tarball 或自定义下载协议；Git 服务对 blob filtering 的支持差异不改变应用语义，必要时只退化为仍然受 sparse checkout 限制的浅层获取。

应用器不校验自身版本是否与目标模板 ref 来自同一个 commit，也不承诺任意脚本版本都能处理任意模板版本。README 必须明确说明跨版本组合不保证兼容，调用者负责选择应用器版本；应用器只记录实际获取到的模板 commit，避免为了兼容性校验引入额外 bootstrap 和 schema 协议。

第一版应用器只支持已有 Git 仓库的 apply 模式，不根据目标目录状态隐式切换创建流程。新项目的文档流程可以保持简单：`mkdir <project>`、`git init`，再运行初始化脚本；初始化脚本负责让仓库达到应用器要求的状态（包括必要时创建首个提交），随后再应用指定模板。应用器本身不负责猜项目名称、初始化远端或创建用户提交。

已有仓库的 apply 模式默认把完整模板快照交给 Git 原生 squash merge，只维护一份小型根目录 denylist，完全跳过不能触碰的项目身份和工作区控制文件。第一版保护根目录 `.gitignore`、`AGENTS.md`、`AGENTS.*`、`LICENSE*`、`LICENCE*`、`COPYING*` 和 `NOTICE*`；README、普通 docs、workflow 和其他模板文件不在保护集合中，交给 Git merge 和用户审查。被保护路径从临时模板 commit 中排除，应用器继续执行并输出 `HINT`，列出被跳过的路径。

`templates.toml` 中的 render 规则决定模板快照如何生成，`[apply]` 只声明 denylist 和必要的特殊提示，不维护完整文件 allowlist，也不把普通路径筛选逻辑硬编码进应用器源码。`.gitattributes`、`.gitmodules`、CODEOWNERS 和其他特殊路径暂不默认保护，等真实迁移样本证明风险后再单独决策。

应用器的事务语义与 Git squash merge 保持一致：无冲突时返回 `0`，打印仓库、模板、ref、commit SHA 和保护路径 HINT；有冲突时返回非零，但保留 index stages 和工作树现场，不创建 `MERGE_HEAD`，也不替用户执行 `git add` 或 `git commit`。输出必须给出 `git status`、`git diff`、解决后 `git add`、`git diff --check` 和使用 `git reset --hard HEAD` 取消整次应用的提示。

应用器使用本地临时 Git 仓库进行集成测试，覆盖保护 denylist 与 HINT、squash merge、冲突 index stages、退出码、无 `MERGE_HEAD`、取消操作以及用户解决冲突并提交后的单父提交历史；这些行为不依赖远端 GitHub 测试。

`v0.1.0` 的应用器是一次性初始化或首次应用工具，不在目标仓库保存上一次 `Template-Commit` 状态，也不实现模板升级的增量三方 merge base。每次应用都把当前模板快照视为与目标仓库无共同历史的独立 squash merge；重复 apply 可能产生 add/add 冲突，不属于受支持工作流，也不保证结果构成有效升级。应用器仍打印本次模板 commit 供用户自行记录，但 provenance 跟踪、状态文件和低冲突升级协议只有在真实使用证明必要时才另行设计。

### 阶段二：建立共享行为清单

1. 比较三个模板中的同路径文件和任务定义。
2. 为每项差异标记“有意差异”或“无意漂移”。
3. 按“完全共享”“共享骨架加参数”“模板专属”完成分类。
4. 第一批只提取 `LICENSE`、`cliff.toml`、`hk.pkl` 和 `docs/pnpm-workspace.yaml`；其他 tracked 路径全部按现有 Git tree 完整迁入对应 overlay，锁文件同样先保持各模板独立所有权。

### 阶段三：提取 mise 共享模块

1. 定义共享的 repository task catalog。
2. 定义 Go 和 Rust 的语言 adapter。
3. 统一 `check`、`fix` 和 release helper 的组合逻辑。
4. 保持每个模板的 `mise run check`、`mise run fix` 等用户接口不变。
5. 为共享任务和模板任务分别设置验证入口。

### 阶段四：收敛 CI 和发布流程

1. 基线迁移先把现有 workflow 作为权威全文件 overlay 原样生成，不在重构过程中顺带统一触发器、缓存、审计或 job 拓扑。
2. 后续让 workflow 只调用稳定的 mise 任务，并逐个确认需要保留的行为合同。
3. 确认合同后，再通过中性 workflow layout 和模板专属 fragment 生成完整、自包含的 workflow；语言缓存、审计、job 拓扑和发布矩阵仍留在对应 overlay。
4. 原生 reusable workflow 和 composite action 只在有助于最终项目维护时使用，并验证 release、prepare-release、docs 和普通 CI 的权限与触发行为没有回归。

第一版 CI 不做路径影响分析：每次变更都运行无模板参数的根级 `mise run sync:check` 和 `mise run check`。common、Go 和 Rust 模板使用独立并行 job、独立失败状态和稳定缓存 key；只有模板数量或检查成本明显增长后，才根据 shared 和 overlay 路径计算影响范围。

Renovate 仓库级只读取根目录生成后的完整 `renovate.json`，不会把模板子目录中的配置当成独立仓库配置合并。根配置只扫描和修改根工具、`shared/**` 与 `overlays/**` 中的真实来源，并忽略 `templates/**` 生成输出。依赖更新 PR 需要通过根级 `mise run locks:update <template>` 和 `mise run render` 产生锁文件与模板快照；`mise run sync:check` 阻止只更新来源或只更新输出一侧的变化合并。机器人直接修改生成输出属于所有权违规。

模板自带的完整 `renovate.json` 由共享 base 和对应 profile 生成。公共规则在来源中只维护一份，但在模板快照中物化为可独立运行的完整配置；已有外部项目不会自动获得中央策略变更，`v0.1.0` 只支持人工移植新规则，不把重复 apply 描述为升级方式。

### 阶段五：加入生成与防漂移检查

1. 实现确定性的模板渲染或文件物化工具。
2. 实现 `render [template]` 和 `sync:check [template]`，省略参数时处理全部正式模板。
3. 在 CI 中重新生成派生文件并检查工作树差异。
4. 为共享模块增加行为测试，避免只比较文本而漏掉任务语义变化。

### 阶段六：远端切换和清理

1. 在 `v0.1.0` 通过公开分发验证后，将新的 monorepo 设为唯一维护入口，不设置双写期。
2. 更新文档、贡献指南和仓库链接。
3. 将旧 GitHub Go 模板仓库归档；Forgejo 仓库允许重建，Rust 不额外创建归档远端；第一阶段不生成会重新引入同步负担的反向镜像。
4. 稳定运行一段时间后，再评估是否需要 Josh 提供独立的过滤仓库视图。

## 历史迁移待验证项

三个旧仓库各自拥有独立历史，其中 Go 模板当前使用 colocated Jujutsu。新 monorepo 不要求完整导入这些历史，但迁移方案需要满足：

- 不重写或覆盖旧 GitHub Go 仓库历史，并保留其 tags、GitHub Releases 和自动发布记录。
- Forgejo 旧仓库不属于必须保留的历史合同，允许在迁移后重建。
- 能追溯 monorepo 中每个 overlay 和模板输出来自哪个旧仓库、基线 commit 和 Git tree。
- 避免在有未提交改动时复制当前工作树，并记录冻结时的工作树状态。
- 明确新 monorepo 采用从 `v0.1.0` 开始的全新 tag namespace 和统一发布规则，不导入旧仓库 tags。

迁移时应在临时目录冻结三个旧仓库的基线工作树，生成 overlay 和模板快照，再以一个明确的迁移提交建立新 monorepo。正式操作前仍应演练文件树、来源映射和发布归档结果。

## 验证标准

迁移完成至少应满足：

1. 修改一个完全共享文件，只需改动一个来源位置。
2. `mise run sync:check` 能发现任意模板派生内容被手工修改或未重新生成。
3. 修改一个正式模板的 slot binding，只改变引用该 binding 的生成结果；未知 slot、必填 slot 缺失、slot 重复声明和输出冲突在写入快照前失败。
4. 三个模板均能独立执行其 `mise run check`。
5. 模板自身检查在禁用父级和全局 mise 配置后通过，不依赖 `shared/`、根级 mise 任务或 monorepo 远程配置。
6. Go 和 Rust 的锁文件均由原生包管理命令生成，没有手工编辑。
7. CI workflow 中不再重复维护可由 mise 任务或共享渲染来源表达的逻辑，同时保留显式的缓存、权限、job 拓扑和发布矩阵差异。
8. 根仓库和三个模板的完整 Renovate 配置均能由共享来源重新生成并通过 Renovate 配置验证，不引用本 monorepo 的远程 preset。
9. 发布流程的版本、tag、release notes 和资产打包行为经过端到端验证，首个公开 tag 为不可移动的 `v0.1.0`。
10. 文档明确区分 monorepo 维护者工作流、已有仓库的模板应用流程，以及 `mkdir <project>`、`git init`、初始化脚本的新项目流程。

## 风险

### 过度生成

如果把所有文件都模板化，维护者会难以直接理解最终输出。只对确实共享且会漂移的内容使用生成；简单、稳定、完全一致的文件优先直接复制或映射。

### Slot 接口膨胀

layout 的 slot interface 必须按行为语义划分，不得退化为与具体文件行、step 或 key 一一对应的插入点。新增 slot 如果只服务于一个模板中的一小段条件，应优先把完整文件或 fragment 留在对应 overlay；禁止通过 `extra_1`、`before_*` 等无语义 slot 模拟任意文本拼接。提交生成快照并对所有正式 profile 做全量验证，避免维护者只能通过追踪大量绑定理解最终结果。

### 错误抽象差异

Go 和 Rust 的缓存、审计、构建和发布并不完全相同。共享模块应统一意图和接口，不应为了文本一致而隐藏真实的平台差异。

### 锁文件冲突

monorepo 会同时存在 mise、Go、Cargo 和文档依赖锁文件。每类锁文件必须由对应工具更新，并在任务和 Renovate 配置中明确作用目录。

### Tag 和发布冲突

旧仓库都可以使用 `vX.Y.Z`。新 monorepo 使用全新的单一 tag namespace 和统一 release，旧 tag 只作为归档信息，不直接迁移进新仓库。

### 本机配置掩盖问题

根级 mise 可以继承工具和环境，但模板检查必须设置 `MISE_CEILING_PATHS` 和 `MISE_GLOBAL_CONFIG_FILE=/dev/null` 排除父级与全局配置。render 规则、symlink 越界检查和模板自身 read-only 检查共同避免输出依赖 monorepo 隐式状态。

## 暂缓 Josh

Josh 可以在未来把 monorepo 的不同 workspace 暴露成可读写的独立 Git 视图，但当前优先解决共享模块和生成模型。只有出现以下明确需求时再评估 Josh：

- 使用者必须通过三个独立 Git URL 克隆模板。
- 不同模板需要独立权限或可见性。
- monorepo 体积或 CI 作用域开始影响日常使用。
- 团队愿意维护 Josh CLI 或 proxy 的访问链路。

## 当前实施状态

首轮等价基线已经完成：三个权威仓库的 commit、Git tree 和干净状态已记录；`shared/`、`overlays/`、`templates/` 和 `templates.toml` 已建立；四个已确认共享文件进入 `shared/static/`，其他 tracked 文件完整进入对应 overlay。`render [template]`、`sync:check [template]` 和 `check [template]` 已可用，renderer 已实现 static、精确路径规则、layout、slot、fragment、symlink 安全、executable bit、原子替换和 Git ignore-aware 只读比较。三份生成模板的 Git tree SHA 与冻结基线完全一致，根级全量检查通过。

首次应用器已经完成：Python entrypoint 和 Bash fallback 均以 sparse fetch 获取指定 ref，通过无父临时 commit 和 Git squash merge 把选定模板应用为 staged changes；保护 denylist、detached HEAD、colocated Jujutsu、冲突 index stages、取消操作和用户解决后单父提交历史均由本地 Git 集成测试覆盖。默认仓库为 `https://github.com/YewFence/template.git`，可通过 `--repo` 覆盖。

`mise.ci.toml` 与锁文件批次已经完成：shared layout 拥有公共维护任务，Go/Rust/common 通过四个语义 slot 注入真实差异；三个 overlay 提供 monorepo-only 原生命令 adapter，根级 `locks:update [--bump] <template>` 实现 staging、输出边界、固定 overlay 回写、目录回滚、重新 render、同步检查和模板检查。三模板真实原生命令均已执行并验证。

下一阶段按以下顺序推进：

1. 逐项收敛 workflow 和 Renovate 的行为漂移；把确认后的共同合同提取为共享 layout、slot 和结构化配置，并实现 `actions:update` 的确定性回写流程。
2. 添加 monorepo 根级 GitHub Actions workflow，调用已经稳定的同步检查、三个模板检查和应用器集成测试。
3. 演练 `v0.1.0` release、公开分发和无双写远端切换，不直接改动三个现有仓库的历史。
