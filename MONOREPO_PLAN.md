# 模板 Monorepo 计划

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

`templates.toml` 是 `render-template`、`apply-template` 和 `init-project` 共享的唯一配置合同，登记正式模板名称、按输出路径分组的 named-slot bindings、整文件省略或跨侧同名输出选择的显式路径规则、`[apply]` 的保护路径和 HINT，以及每个 profile 的项目实例化 schema；不登记 layout 路径或 context。生成器自动发现 shared 和当前 overlay 的来源并按输出路径取并集，不要求配置维护所有静态文件的完整清单。只在一侧存在的路径默认直接采用，也可显式 `omit`；两侧重复的路径必须显式选择来源或省略。未知 slot、必填 slot 缺失、slot 重复声明、同一侧输出冲突和未声明的跨侧冲突都必须失败。

实例化 schema 与 validation fixture 也归对应 `[templates.<name>]` profile 所有。配置从当前应用器版本静态支持的 metadata 字段中选择必填集合，并声明 token map 和有限的声明式派生值；validation metadata 位于明确的专属命名空间，只服务临时 staging，不能作为用户 CLI 的隐式默认值。Python package 不以模板名称分支执行不同实例化流程，但应用器版本可以静态定义自己支持的字段和 transform 词汇。

第一版 schema 只包含 `required` 字段列表、平面 `tokens` 映射、有限 `derived` 声明和 `validation.metadata` 值。字段不配置独立对象、prompt/help 文案、用户默认值、正则表达式或任意命令；普通静态 argparse 提供当前版本全部已知参数的帮助和 TTY 提示，缺失字段仍按 D59 处理。

`init-project` 不做两阶段动态参数注册。当前应用器版本一次解析 `target`、`--repo`、`--ref`、`--template` 以及全部静态支持的 metadata options；获取模板配置后，只校验所选 profile 的必填集合、拒绝无关字段并构造 token 值。若目标 ref 声明当前应用器不认识的字段、token source 或 transform，直接报告不兼容，不尝试适配不同版本 schema。裸 `--help` 始终离线并展示当前版本的完整参数集合。

第一版 derived transform 白名单只有 `hyphen-to-underscore` 与 `json-string`。Rust 使用前者从 Cargo package 名生成源码可引用的 crate identifier；TypeScript 和 YAML 的字符串位置使用后者生成包含双引号的正确转义值。Markdown 等 raw 文本位置继续使用原字段 token。配置必须为不同上下文声明不同 token，不支持 transform 链、任意表达式或模板提供自定义编码器。

Token 语义固定为：`PROJECT_NAME` 只用于人类可读展示；`PROJECT_DESCRIPTION` 用于 raw 文本，`PROJECT_DESCRIPTION_JSON` 用于 JSON/TypeScript/YAML 字符串；`GITHUB_OWNER`、`REPO_NAME` 用于 GitHub 身份和 URL；`GO_MODULE` 只用于 Go module/import；`CARGO_PACKAGE` 只用于 Cargo package；`RUST_CRATE_IDENT` 用于 Rust 源码引用；`BINARY_NAME` 用于 executable、命令路径和 release packaging。Go 的 `cmd/your-cli` 路径、completion 文档和命令示例必须使用 `BINARY_NAME`，不能把显示名当作 binary。

模板来源不保留身份相关 legacy sentinel。`your-cli`、`rust-template`、`rust_template`、`github.com/example/your-cli` 等旧字面量在 manifest、源码、测试、mise task、脚本、docs package 和路径中都必须迁移为显式 token；实例化阶段不得再按字面量做隐式替换或 fallback。

残留 identity sentinel 由对应 `overlays/<name>/mise.toml` 的 monorepo-only validation adapter 检查。Go、Rust 等历史名称列表归各自 overlay 所有，不提升到 shared、不渲染进模板，也不写入 `template-tool`；adapter 在依赖生成与最终项目检查前扫描实例化 staging，命中即 fail fast。

所有 metadata 字段和 validation fixture 值必须是非空单行字符串。工具拒绝 NUL、ASCII 控制字符以及前导或尾随空白，不静默 trim，也不在显式 derived transform 之外修改大小写、连字符或其他字符。普通空格、标点和 Unicode 保持原样。第一版不复制 GitHub owner、Go module、Cargo package 等生态命名规则；实例化后的原生 manifest 由对应工具与最终 `mise run check` 负责语义校验。

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

### 模板依赖状态

模板交付物不保存预生成依赖状态。`shared/`、`overlays/<name>/static/` 和 `templates/<name>/` 中不提交模板的 `mise.lock`、`mise.ci.lock`、`Cargo.lock`、`go.sum`、`docs/pnpm-lock.yaml` 等原生命令输出；模板 workflow 也不保存 Action commit digest，只声明 `actions/*@vN` 等兼容版本线。monorepo 根 `mise.lock`、`tools/template-tool/uv.lock` 和根 workflow digest 属于维护环境，继续精确锁定。

模板源码声明生态认可的兼容版本线，而不是机械地把所有版本裁成 major。稳定生态通常声明 major；pre-1.0 工具可以保留 minor 兼容线；Go Modules 等不支持范围的生态继续保存合法的具体版本。Rust `rust-version`、Go language directive 和项目自身版本表达兼容性或项目身份，不属于依赖锁定。

刚 render 或 apply 的结果称为未引导模板，不保证直接通过 `mise run check`。用户需要按文档依次生成 mise 锁、规范化语言依赖、生成文档锁并通过 pinact 固定 Action digest；完成后才成为应当通过检查的已引导项目。模板不新增 `mise run bootstrap` 聚合入口，文档直接暴露真实命令。

模板省略锁定状态不代表生成项目放弃可复现性。用户完成引导后必须把 `mise.lock`、`mise.ci.lock`、Cargo/Go 等语言依赖状态、`docs/pnpm-lock.yaml` 和 pinact 对 workflow 的修改加入版本管理。模板继续保留 `MISE_LOCKED`、Cargo `--locked`、pnpm frozen lockfile 和 pinact 离线检查；相关路径不得加入 `.gitignore`。

新项目首次引导和 monorepo staging 验证都运行模板的 `deps:update`，把依赖解析到执行当天兼容版本线内的当前版本。Go 因 `go.mod` 必须保存具体版本，需要通过 `go get -u ./... && go mod tidy` 把模板中的历史具体版本更新到当前兼容版本；Rust 在无 `Cargo.lock` 时通过 `cargo update` 建立当前解析。`deps:fix` 仍表示只规范化当前依赖状态，不主动升级。应用到已有项目时不自动运行更新，用户先审查 manifest 合并结果再决定。

staging validation 不直接把含 metadata 占位符的原始蓝图当作最终项目检查。根工具先 render 未实例化蓝图，再使用固定、合成的 validation metadata 调用与 `init-project` 相同的实例化管线；随后 overlay adapter 才生成 mise、语言、文档和 Action 临时状态并运行模板自己的 `mise run check`。fixture 只存在于 staging，流程结束后随目录删除，不写入 shared、overlay、模板快照或公开 CLI 默认值。`sync:check` 仍只验证声明式来源与未实例化快照。

项目实例化不是第二轮 Jinja render。`template-tool` 扫描可识别的 UTF-8 文本文件及相对路径组件，并替换 profile 显式声明的 `{{UPPER_SNAKE_CASE}}` metadata token；GitHub Actions 的 `${{ ... }}`、普通双大括号和二进制内容不参与。替换结束后如仍存在未识别的 uppercase metadata token，实例化直接失败。路径替换先计算完整目标路径计划，要求路径 token 值为单个安全组件，拒绝 `/`、`\\`、空值、`.`、`..` 和控制字符；目标不得越出 staging root，路径碰撞、既有目标或文件/目录类型冲突直接失败。Go 与 Rust 的差异只通过 token map 和少量声明式派生值进入，不提供按模板执行任意 Python、shell、Go 或 Rust hook 的扩展点。

文档站点继续使用 pnpm。aube 默认生成 `aube-lock.yaml`，而 Renovate npm manager 当前只正式维护 npm、pnpm 和 Yarn 的标准锁文件名，无法为 aube 原生锁文件提供本方案要求的 lockfile maintenance。模板因此声明 pnpm 兼容版本线，用户和 validation adapter 生成 `docs/pnpm-lock.yaml`，日常任务继续使用 frozen lockfile；这是按 CLI 偏好在能力不足时显式回退，而不是同时维护两套包管理器状态。

validation adapter 只要求文档 lockfile 生成命令成功，不在普通模板验证中运行 `mise run docs:build`。临时引导完成后的唯一项目检查入口仍是模板内置 `mise run check`；文档站点实际构建留给生成项目自己的 CI，未来需要扩大基础检查范围时再单独确认。

文档任务采用三层语义：`docs:install` 使用非 frozen 安装完成首次解析并安装依赖；`docs:lock` 使用 `pnpm install --lockfile-only` 只生成 `docs/pnpm-lock.yaml`；`docs:install:locked` 使用 frozen lockfile 只消费已提交状态。`docs:build`、`docs:dev` 和 `docs:preview` 依赖 `docs:install:locked`，不能通过构建或预览隐式更新依赖。

`init-project` 先在外部工具中完成项目实例化；生成项目随后按以下标准顺序完成依赖引导：`mise trust`、`mise -E ci lock`、`mise install --locked`、`mise run deps:update`、`mise run docs:install`、`mise run actions:update`、`mise run hooks:install`、`mise run check`。validation adapter 使用 `docs:lock` 替代 `docs:install`，不创建 `node_modules`。生成项目不再提供 Go 专属 `mise run init`，项目身份初始化也不属于依赖引导任务。

根 CI 除 push、pull request 和手动触发外，每周运行一次相同的 staging validation，以发现兼容版本线在无模板源码变更时的上游破坏。定时任务只读 monorepo 来源，失败不自动修改版本、不回写锁文件、不创建 PR；维护者人工决定是否调整模板声明。

每周 validation 不运行 `mise -E ci run audit`，也不演练 release workflow 或平台打包矩阵。漏洞结果属于已引导用户项目的 scheduled audit，common audit 仍是 placeholder；release helper 与 package adapter 继续由独立显式测试覆盖。定时失败只表达当前兼容解析无法通过基础 `mise run check`。

根 CI 第一版删除 Go/Rust 模板项目缓存：模板快照不再有可用于 `hashFiles` 的锁文件，动态 staging 也不是 workflow 预先可寻址的固定 workspace。只保留 mise-action 的工具安装缓存；生成项目自己的 workflow 继续使用已提交锁文件驱动语言缓存。只有真实耗时证明必要时，才另行设计外置 target 或 manifest-based staging cache。

monorepo 检查必须在临时 render 目录中模拟这次引导。每个 `overlays/<name>/mise.toml` 提供 monorepo-only `check <template-root>` adapter，拥有该模板的原生命令与执行顺序，并在状态生成完成后调用 staging 模板自身的 `mise run check`。Python 工具只负责临时 render、隔离 mise 与 Git 环境、调用 adapter、聚合错误和删除 staging，不理解语言命令，也不把生成结果回写到真实来源或模板快照。

因此删除 `templates.toml` 中的 `[templates.<name>.locks]`、根 `locks:update` 任务与 CLI、Python 的允许输出检查、来源回写和回滚实现。`sync:check` 仍然只比较声明式来源与未引导模板快照；临时验证产生的锁文件、校验文件和 workflow digest 修改随 staging 目录一起丢弃。

`locks:update` 不保留兼容别名或改造成只读 smoke test。根 `check` 是唯一执行 staging 依赖状态生成与模板项目检查的接口；`update` 一词只用于真实用户项目中会保存结果的 `deps:update`、`actions:update` 等任务。

根 `actions:update` 只处理 monorepo `.github/workflows/**`，直接调用 `pinact run --update .github/workflows`。删除 template-tool 的 actions updater、CLI 与事务测试；模板来源不参与根 digest 更新，也不触发 render。少量根 workflow 的部分本地修改由普通 Git diff 审查和恢复，不继续维护跨来源回滚抽象。

## 根级 mise 职责

外层 `mise.toml` 是 monorepo 的操作入口，而不是模板项目自身配置的替代品。第一版提供以下稳定任务：

| 任务 | 职责 |
| --- | --- |
| `render [template]` | 从共享来源更新指定模板；省略参数时更新全部正式模板 |
| `sync:check [template]` | 只读检查指定模板；省略参数时检查全部正式模板 |
| `check [template]` | 在临时目录完成模板引导并执行完整检查；省略参数时检查全部正式模板 |
| `actions:update` | 更新并固定 monorepo 维护环境的 GitHub Actions 引用 |

`render`、`sync:check` 和 `check` 的可选 `template` 参数只能是 `common`、`go-cli` 或 `rust`，省略时统一表示全部正式模板。复杂实现和全量模式的错误聚合放入 `tools/template-tool/` 的 Python package，mise 只登记稳定接口、参数和任务元数据。

模板检查不在 `templates/<name>` 原目录生成状态。Python 为每个模板创建临时完整 raw render，使用 validation fixture 实例化路径与内容，再为实例化后的 staging 创建外部 Git dir/index，随后从 `overlays/<name>` 调用验证 adapter；调用设置 `MISE_CEILING_PATHS=<monorepo-root>`、`MISE_GLOBAL_CONFIG_FILE=/dev/null`、overlay 与 staging 的临时 trusted paths，并清空 `RUSTFLAGS`，避免加载根配置、用户全局配置或本机 Cargo linker 设置。不使用 `MISE_CONFIG_FILE`，不修改用户持久 trust 状态。

验证 adapter 先生成 staging 所需的 mise、语言、文档和 Action 固定状态，再运行模板内现有的 locked/frozen 检查。检查产生的 tracked 或 untracked 变化不回写真实仓库，整个 staging 在任务结束后删除。发布前运行根级 `mise run sync:check`、`mise run check` 和应用器集成测试即可，不再存在独立锁文件更新或回写流程。

## 共享内容分类

迁移前先把现有文件分为以下三类：

### 完全共享

内容在三个模板中应当完全一致。这类文件可以直接来自 `shared/static/`。第一批提取范围已经确定为：

- `LICENSE`
- `cliff.toml`
- `hk.pkl`
- `docs/pnpm-workspace.yaml`

`docs/pnpm-lock.yaml` 是项目引导时生成的依赖状态，不属于 shared 或 overlay render 来源；三个模板都不再提交它。外层验证可在各自 staging 中生成该文件，但结果不会进入共享分类或模板快照。

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

模板使用者不下载 release 归档，而是通过应用器从 monorepo 的指定 ref 获取并应用完整模板快照。Python 工具位于 monorepo 根目录的 `tools/template-tool/`，提供 `render-template`、`apply-template` 和 `init-project` 三个独立 entrypoint；Bash fallback launcher 位于 `scripts/apply-template`，它们都和模板内容一起版本控制。`apply-template` 与 `init-project` 的 `--repo` 默认使用官方 monorepo 地址但允许覆盖，`--ref` 决定要获取的 `templates/<name>` 快照版本，`--template` 决定目标模板；`--ref` 与 `--template` 都必须显式提供，不默认回落到 `main`。

uvx 示例必须让应用器来源的 `@<ref>` 与命令的 `--ref <ref>` 使用同一个显式值；从 clone 本地运行时使用 `--repo <monorepo-path> --ref HEAD`。工具不尝试证明两个 ref 相等，也不承诺错配版本兼容；显式参数只负责避免安装固定应用器后无意获取当前 `main`。

当前实现决策是以同一个 Python package 承担渲染、项目实例化与应用逻辑，共享模板约定、配置解析、Git 调用和临时目录处理，但通过独立 entrypoint 保持维护者接口、已有仓库入口与新项目入口分离。使用 uv 的用户可以通过 `uvx --from git+<repo>@<ref>#subdirectory=tools/template-tool apply-template` 或 `init-project` 直接选择并运行指定 Git ref 的应用器；Bash launcher 只作为没有 uv 时的 fallback，不承载 apply policy 等业务逻辑。Python 实现优先考虑标准库，模板渲染明确使用 Jinja2；其他第三方依赖和模块拆分在实现阶段根据真实复杂度决定。Python 源文件不使用绑定 uv 的 shebang，依赖与锁文件通过 uv 原生命令维护，不手工编辑。

uv 入口是正式支持路径，负责从指定 Git ref 解析、安装并运行应用器及其依赖。Bash fallback 只做 best-effort：它获取应用器源码并尝试使用系统 Python 运行，不实现 venv、pip、锁文件解析或第三方依赖安装；如果某个应用器版本无法在当前系统 Python 环境中直接运行，launcher 必须清晰失败并提示改用 uv。README 明确说明 Bash fallback 不保证覆盖所有应用器版本。

第一版正式支持 Linux 和 macOS；Windows 只支持 WSL，不承诺原生 Windows。Python 实现避免无必要的 Linux 专用路径假设，但 symlink、executable bit、Bash fallback 和 Git worktree 行为只在正式支持平台验证。

应用器必须沿用安全的目标仓库语义：目标 Git 工作树默认要求干净，模板变更进入暂存区供审查，应用器不替用户提交；应用过程失败时不留下半成品。应用器 fetch 后必须解析并打印最终 commit SHA，便于记录 `Template-Commit` 来源；默认跟随 `main` 是便利性选择，不能被误解为不可变输入。

干净仓库要求覆盖 tracked 修改、staged 修改和普通 untracked 文件，等价于 `git status --porcelain --untracked-files=normal` 为空；被 `.gitignore` 忽略的缓存不阻止应用，但路径占用由 Git 自己拒绝。应用器不提供 `--force`、自动 stash 或自动清理，用户必须在运行前自行处理现有工作。

应用器支持 detached HEAD 和 colocated Jujutsu 仓库，但 `HEAD` 必须指向真实 commit，不能是尚无提交的 unborn branch；目标仓库也不能存在进行中的 merge、rebase、cherry-pick 或 revert。应用器只操作 Git index 和工作树，不移动 branch、不创建提交、不调用 `jj`；输出 HINT 提醒用户完成、解决或取消本次应用后再继续普通 `jj` 操作。

应用器启动时打印最终仓库、模板、ref 和解析后的 commit SHA。模板路径始终由 `--template` 和固定的 `templates/<name>` 布局推导，不接受独立模板目录 URL，避免应用器与 monorepo 目录约定脱节。

私有仓库和其他 Git 服务的认证完全交给 Git：`--repo` 接受 Git 支持的 HTTPS 或 SSH 地址，应用器使用用户现有的 credential helper、GitHub CLI credential、SSH agent 和 SSH 配置，不读取或记录 token，也不实现额外的 GitHub API 认证流程。认证失败、网络失败和 ref 不存在都直接失败并保留清晰错误。

应用器使用 Git 原生的浅层 sparse checkout 获取输入：临时仓库只检出应用器本身和目标 `templates/<name>` 路径，不下载或展开无关模板与文档内容。第一版不引入 GitHub API、release tarball 或自定义下载协议；Git 服务对 blob filtering 的支持差异不改变应用语义，必要时只退化为仍然受 sparse checkout 限制的浅层获取。

应用器不校验自身版本是否与目标模板 ref 来自同一个 commit，也不承诺任意脚本版本都能处理任意模板版本。README 必须明确说明跨版本组合不保证兼容，调用者负责选择应用器版本；应用器只记录实际获取到的模板 commit，避免为了兼容性校验引入额外 bootstrap 和 schema 协议。

第一版应用器不根据目标目录状态隐式切换创建流程。已有历史的干净 Git 仓库使用 `apply-template`；新项目执行 `mkdir <project>`、`git init` 后使用独立 `init-project` 入口。该入口只接受干净、unborn 且参数路径就是 repository root 的仓库，使用普通 `git commit --allow-empty -m "chore: initialize repository"` 创建必要的无父根提交。随后它获取未实例化模板，在外部工具控制的临时树中完成项目名称、描述、仓库身份和语言专属 module/crate/binary 等一次性物化，再把实例化结果复用相同 Git 应用逻辑写成 staged changes。它不绕过用户 identity、签名或 hooks，不初始化远端，也不替用户提交模板内容。

`init-project` 的项目 metadata 以显式 CLI options 作为唯一稳定、可脚本化的正式接口。连接交互式终端时，工具可以用提示补齐调用方没有提供的必填项；在管道、CI 或其他非交互环境中，缺少任何必填项都直接失败。提示文字和提问顺序不属于兼容性合同，工具也不根据 Git remote 猜测 owner、repository 或其他项目身份。

所有模板共享 `--project-name`、`--description`、`--github-owner` 和 `--repo-name` 四个必填项目身份字段。Go CLI profile 额外要求 `--go-module` 与 `--binary-name`；Rust profile 额外要求 `--cargo-package` 与 `--binary-name`；common 不增加语言字段。`project-name` 只表达面向人的显示名称，不能同时充当命令名、Cargo package 或 Go module。CLI 根据 `--template` 选择对应 schema，不要求 common 调用方传无意义的语言参数，也不让 Go 与 Rust 参数泄漏进共享接口。

模板蓝图的 README 采用单文件合同：overlay 只提供一个包含项目 metadata 占位符的 `README.md`，不再同时交付模板使用指南和 `README.template.md`。`init-project` 在外部临时树中直接替换该文件及其他项目内容的占位符，干净新项目得到的就是最终项目 README；`apply-template` 不自动实例化或特殊消费 README，而是把它作为普通模板文件交给既有 Git staged apply 和用户审查。统一使用、自举与应用器说明迁到根 README，overlay README 只保留模板特有功能、结构和语言行为。

根目录 `README.md` 统一承载所有模板的外部使用说明，包括 `apply-template`、`init-project`、metadata 参数和依赖引导命令。`overlays/<name>/static/README.md` 只描述对应模板的功能、项目结构和语言特有行为，不重复维护应用器流程；模板特有说明可以在根 README 中链接到对应章节或来源。

AGENTS 采用同样的单文件合同：overlay 只提供一个面向生成项目的 `AGENTS.md`，实例化工具直接替换其中的项目 metadata 和语言规则。模板维护者专属的说明迁出用户交付物；已有项目的 `apply-template` 仍保护 `AGENTS*`，不自动替换或合并该文件。

`apply-template` 仍只为已有项目执行纯 staged apply，不自动执行项目实例化，也不重写已有项目的名称、module、crate、remote 或 Git 历史。项目实例化能力属于同一个 `template-tool` 深模块，但只由新项目入口自动调用；这让 Go、Rust 和 common 共用一致的一次性实例化边界，同时避免已有项目入口获得危险的隐式身份修改能力。模板蓝图直接删除 Go 的 `mise run init`、`tools/init-template`、`tools/apply-existing`、`README.template.md` 和 `AGENTS.template.md`，不保留兼容任务或工具。

因此已有项目 apply 的 staged tree 可以包含 `{{PROJECT_NAME}}`、`{{GO_MODULE}}`、`{{BINARY_NAME}}` 以及 `cmd/{{BINARY_NAME}}/` 等合法蓝图 token。`apply-template` 不接受 metadata、不自动替换或重命名，也不因这些 token 存在而失败；成功输出增加未实例化 HINT，提示用户结合 `git status`、`git diff --cached` 和 uppercase token 搜索审查、重命名或删除。该 HINT 不启动交互式项目实例化。

已有仓库的 apply 模式默认把完整模板快照交给 Git 原生 squash merge，只维护一份小型根目录 denylist，完全跳过不能触碰的项目身份和工作区控制文件。第一版保护根目录 `.gitignore`、`AGENTS.md`、`AGENTS.*`、`LICENSE*`、`LICENCE*`、`COPYING*` 和 `NOTICE*`；README、普通 docs、workflow 和其他模板文件不在保护集合中，交给 Git merge 和用户审查。被保护路径从临时模板 commit 中排除，应用器继续执行并输出 `HINT`，列出被跳过的路径。

`init-project` 使用独立的 clean-target apply policy。其目标已经是干净、unborn 且没有 untracked 内容的仓库，不套用已有项目 denylist，允许实例化后的 `README.md`、`AGENTS.md`、`.gitignore`、许可证、notice 及其他模板文件完整进入 staged changes。两个入口共享 sparse fetch、临时 commit 和 squash apply 内核，但 protected policy 由目标生命周期决定。

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

Renovate 仓库级只维护 monorepo 自身环境，包括根 `.github/**`、根 `mise.toml`/`mise.lock` 和 `tools/**` 等维护依赖；不扫描 `shared/**`、`overlays/**` 或 `templates/**` 中的模板版本声明。模板蓝图的兼容版本线由维护者人工调整，避免机器人把有意稳定的大版本或 pre-1.0 minor 线持续改成新的设计选择。

模板自带的完整 `renovate.json` 仍由共享 base 和对应 profile 生成，并继续启用语言 manager、Action digest pinning 和 lockfile maintenance；它服务的是已引导用户项目，不代表根 Renovate 可以更新模板蓝图。公共规则在来源中只维护一份，但已有外部项目不会自动获得中央策略变更，`v0.1.0` 只支持人工移植新规则，不把重复 apply 描述为升级方式。

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

首次应用器的 Git 基线已经完成：Python entrypoint 和 Bash fallback 均以 sparse fetch 获取指定 ref，通过无父临时 commit 和 Git squash merge 把选定模板应用为 staged changes；保护 denylist、detached HEAD、colocated Jujutsu、冲突 index stages、取消操作和用户解决后单父提交历史均由本地 Git 集成测试覆盖。独立 `init-project` entrypoint 已能为干净的 unborn repository 创建普通初始根提交后复用同一应用合同，但尚未实现新确认的外部项目实例化；Go 内置 `mise run init` 和一次性工具仍待迁出。三份正式模板还从当前 monorepo HEAD 通过正式 entrypoint 实际应用到临时仓库，验证 staged 文件、保护路径、commit provenance、零冲突、无 `MERGE_HEAD`、已有仓库 HEAD 不移动和新项目根提交。默认仓库为 `https://github.com/YewFence/template.git`，可通过 `--repo` 覆盖。

上述应用器验证只证明共享 Git 应用内核；新确认的项目实例化、单文件 README/AGENTS 和 `init-project` clean-target policy 尚未实现，后续实现必须更新对应集成测试，不能把旧的 protected-path 结果当作新入口合同。

`mise.ci.toml` 的 shared layout 与四个语义 slot 已完成。旧的 `locks:update`、固定 overlay 回写和回滚实现仍存在于当前代码，但已被本计划中的“未引导模板 + staging 临时验证”合同取代，后续实现需要删除旧路径并把三个 overlay adapter 改为 monorepo-only `check`。

本地收敛阶段已经完成：`ci.yml`、`audit.yml`、`docs.yml`、`prepare-release.yml` 和 `release.yml` 已提升为 shared layout，并通过语义 slot 保留 Go/Rust 审计与项目缓存、文档工具、版本文件和平台构建矩阵差异；三个 audit workflow 都支持默认分支 push、默认分支 PR、每周 schedule 与手动触发。Renovate base/profile、根级事务式 `actions:update`、monorepo 根 CI 和 22 个 template-tool 单元/本地 Git 集成测试均已实现。模板检查使用外部临时 Git dir/index，不再向生成快照写 `.git` 标记，Git-based newline/leak 检查真实覆盖 tracked baseline，同时忽略缓存。

本地验证标准 1–8 与 10 已有实现和直接验证证据：根配置与三个模板配置通过官方 `renovate/renovate:44.13.2` 容器中的 `renovate-config-validator --strict --no-global`。aube 安装路径仍因间接依赖 provenance 降级保护失败，未添加 trust exception，也未改用 npm/npx 绕过。标准 9 的本地 release helper 与 package adapter 已在离线临时 Git 仓库演练通过：三模板均解析 `0.1.0`/`v0.1.0`，notes、changelog、tag 创建和幂等检查成功，common 保持零附件，Go/Rust 各生成一个 Linux x86_64 archive；公开 GitHub release/tag 端到端验证尚未执行。

以下外部发布工作不属于当前本地收敛范围，需未来获得明确授权后执行：

1. 用户创建 `https://github.com/YewFence/template.git` 后添加官方 remote，验证公开 sparse fetch、uvx 应用器与 GitHub Actions。
2. 演练不可移动的首个 `v0.1.0` tag、release PR、GitHub Release 和 Go/Rust 资产发布。
3. 公开验证通过后再执行无双写远端切换与旧仓库归档，不改写三个旧仓库历史。
