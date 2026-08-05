# 决策记录

## 2026-08-06：首批 `mise.ci.toml` 收敛

- **范围**：三份模板的 CI/维护环境配置、shared layout、overlay adapter fragment，以及生成配置绑定。
- **取舍**：公共 release helper 和在线 action 版本检查原样迁移到 shared layout；模板差异只通过 `maintenance_tools`、`audit_tasks`、`release_version_tasks` 和 `release_package` 四个语义 slot 注入。
- **理由**：现有三份 release helper 的命令、输入和失败行为一致，继续复制会保留漂移源；Go、Rust 的工具和打包入口确实不同，不能靠文本合并隐藏差异。
- **聚合任务**：Go 的 `audit` 按 `mod:verify` 再 `vuln:check` 顺序执行，`actions:versions:check` 按 pin 检查再 outdated 检查执行，均使用 mise 任务数组保留 fail-fast 语义。
- **common 行为**：common 的审计和打包仍是明确的 `[PLACEHOLDER]` 成功任务，避免生成后的语言无关模板伪造安全结果或资产路径。
- **生成结果**：普通 `render` 只从 layout、fragment 和现有受管静态文件生成，不运行原生命令；三份 `mise.ci.toml` 快照随后由 renderer 重新物化。

## 2026-08-06：模板交付物取消预生成锁定状态

- **责任域**：模板交付物与 monorepo 维护环境分离。模板交付物不再包含预生成锁文件或 GitHub Action digest；根 `mise.lock`、`tools/template-tool/uv.lock` 和根 workflow 的 Action digest 继续精确锁定。
- **交付状态**：刚 render 或 apply 的模板是未引导模板，不保证直接通过 `mise run check`。用户生成原生依赖状态并固定 Action digest 后，项目才进入应当通过检查的已引导状态。
- **版本声明**：模板声明生态认可的兼容版本线。稳定生态通常声明 major，pre-1.0 工具可保留 minor 兼容线；Go Modules 等不支持范围的生态继续使用具体合法版本，语言兼容性下限和项目自身版本不属于依赖锁定。
- **用户接口**：不增加 `mise run bootstrap` 聚合任务。模板文档直接列出 mise lock、语言依赖规范化、文档 lock、Action pinning 和最终检查等真实命令。
- **项目复现性**：模板蓝图本身不预解析依赖，但已引导项目必须提交 `mise.lock`、`mise.ci.lock`、语言锁定/校验状态、`docs/pnpm-lock.yaml` 和 pinact 修改。模板继续保留 locked、frozen 和 pinned 检查，这些路径不得加入 `.gitignore`。
- **首次解析策略**：新项目引导与 monorepo staging 验证运行 `deps:update`，解析到执行当天兼容版本线内的当前版本；`deps:fix` 继续表示只规范化、不主动升级。应用到已有项目时不自动升级，用户审查 manifest 后自行决定。
- **Node 包管理器**：最终模板继续使用 pnpm 与 `pnpm-lock.yaml`。aube 默认生成的 `aube-lock.yaml` 尚不在 Renovate npm manager 的官方 lockfile 集合中，无法满足生成项目的 lockfile maintenance，因此按项目 CLI 规则回退 pnpm。
- **验证范围**：validation adapter 生成文档 lockfile，但完成引导后只运行模板内置 `mise run check`；当前不追加 `docs:build`，文档站点实际构建不属于模板基础检查。
- **文档任务语义**：`docs:install` 允许首次解析兼容版本并安装，`docs:lock` 只生成 `pnpm-lock.yaml`，`docs:install:locked` 只消费已提交锁文件；`docs:build`、`docs:dev` 和 `docs:preview` 依赖 `docs:install:locked`，避免构建动作隐式改写依赖状态。
- **引导顺序**：`init-project` 完成项目实例化后，新项目依次执行 `mise trust`、`mise -E ci lock`、`mise install --locked`、`deps:update`、`docs:install`、`actions:update`、`hooks:install` 和 `check`。validation adapter 使用 `docs:lock` 代替 `docs:install`，不创建 `node_modules`；生成项目不再提供 Go 专属 `mise run init`。
- **定时验证**：根 CI 每周运行一次 staging validation，重新解析兼容版本线并执行模板 `mise run check`；定时任务不回写来源、不创建更新 PR，失败只提示需要人工调整。
- **定时范围**：每周 validation 不运行 audit 或 release 演练。漏洞检查由已引导项目自己的 scheduled audit 负责，release helper 与打包矩阵继续使用独立显式测试。
- **根 CI 缓存**：第一版删除依赖模板快照锁文件或固定 workspace 的 Go/Rust 项目缓存，只保留 mise 工具缓存。生成项目 workflow 的语言缓存继续使用其已提交锁文件；staging 专用缓存等出现真实性能问题后再设计。
- **验证所有权**：每个 `overlays/<name>/mise.toml` 的 monorepo-only `check` adapter 完整拥有“在 staging 中生成临时依赖状态与 Action digest，再运行模板自身 `mise run check`”的顺序。Python 工具只负责临时 render、隔离环境、Git 基线、调用 adapter 和删除 staging。
- **Validation 实例化**：根 staging validation 在调用 overlay adapter 前，使用固定的合成 metadata 运行与 `init-project` 相同的项目实例化管线。fixture 只存在于临时 staging，不进入模板来源、生成快照或用户接口；`sync:check` 继续验证未实例化蓝图，staging validation 验证实例化后的项目。
- **外层 identity 检查**：各 `overlays/<name>/mise.toml` 的 monorepo-only validation adapter 负责检查实例化 staging 是否残留该模板的 legacy identity sentinel。检查列表不进入 shared、生成模板或用户项目，`template-tool` 也不硬编码历史名称；adapter 在依赖生成和最终项目检查前 fail fast。
- **实例化引擎**：`template-tool` 在可识别的 UTF-8 文本文件和相对路径组件中替换显式声明的 `{{UPPER_SNAKE_CASE}}` metadata token，不把生成树再次交给 Jinja2。替换后残留未知 uppercase token 必须失败；Go/Rust 差异通过 profile token map 和声明式派生值表达，不增加语言专属 imperative hook。
- **路径 token**：路径替换先计算并验证完整目标路径计划，再执行重命名。用于路径的值必须是安全单路径组件，拒绝 `/`、`\\`、空值、`.`、`..` 和控制字符；目标不得逃出 staging root，路径碰撞、既有目标或文件/目录类型冲突均失败。路径与内容共用 token 语法，不允许 hook。
- **Token 语义**：`PROJECT_NAME` 只表示人类可读名称；`PROJECT_DESCRIPTION` 是 raw 描述，`PROJECT_DESCRIPTION_JSON` 是 JSON 转义描述；`GITHUB_OWNER` 与 `REPO_NAME` 表示 GitHub 身份；`GO_MODULE` 表示 Go module path；`CARGO_PACKAGE` 表示 Cargo package 名；`RUST_CRATE_IDENT` 由 Cargo package 名转换而来；`BINARY_NAME` 表示可执行文件、命令路径和 release packaging 名。Go 的 `cmd/your-cli`、completion 文档与命令位置迁移到 `BINARY_NAME`，不再复用 `PROJECT_NAME`。
- **Legacy sentinel 清理**：模板来源中所有会随项目身份变化的 `your-cli`、`rust-template`、`rust_template`、`github.com/example/your-cli` 等旧字面量都必须改成显式 token。实例化引擎不维护这些字面量的兼容替换分支；测试期望、mise task、脚本、manifest、docs package 和路径同样遵守 token map。
- **实例化配置所有权**：`templates.toml` 是 render、apply 和 instantiate 共用的模板 profile 合同。每个 profile 在其中选择必填 metadata 字段、声明 token map、声明式派生值和独立 validation fixture；validation metadata 不是 CLI 默认值。应用器版本静态定义自己支持的字段与 transform 词汇，不承诺读取不同版本模板的未知 schema。
- **最小 schema**：实例化配置只使用 `required` 字段列表、平面 `tokens` 映射、有限 `derived` 声明和 `validation.metadata` 值。第一版不配置字段对象、prompt/help 文案、用户默认值、正则表达式或任意命令插值；CLI help 与交互提示由当前应用器版本的静态参数定义提供。
- **静态 CLI**：`init-project` 使用普通静态 argparse，一次解析全部已知命名 options，不根据远端 `templates.toml` 动态注册参数。所选 profile 只决定哪些已知字段必填以及如何映射 token；传入 profile 未声明的字段或读取到当前应用器不认识的字段/transform 都失败。应用器与不同版本模板之间不提供 schema 兼容保证。
- **显式模板 ref**：`apply-template` 与 `init-project` 的 `--ref` 都是必填参数，不默认使用 `main`。uvx 文档要求应用器来源 `@<ref>` 与模板 `--ref <ref>` 使用同一显式值；本地 clone 使用 `--repo <path> --ref HEAD`。工具不验证两者相等，也不提供错配兼容。
- **Derived 白名单**：第一版只提供 `hyphen-to-underscore` 和 `json-string`。前者生成 Rust crate identifier，后者生成带引号和正确转义、可用于 TypeScript/YAML 字符串位置的 JSON 字符串；raw 文本与编码文本使用不同显式 token。禁止 transform 链、任意表达式和模板自定义编码器。
- **Metadata 通用校验**：所有字段必须是非空单行字符串，拒绝 NUL、ASCII 控制字符和前导/尾随空白，不静默 trim、改大小写或重写标点；普通空格、标点与 Unicode 可以保留。validation fixture 走相同校验。第一版不手写 GitHub、Go、Cargo 等生态命名正则，具体格式交给后续原生工具和项目检查。
- **删除旧合同**：移除 `[templates.<name>.locks]`、根 `locks:update`、Python 回写与回滚实现，以及任何把 staging 生成状态写回 `overlays/<name>/static` 或 `templates/<name>` 的逻辑。临时检查产生的文件和修改随 staging 一并丢弃。
- **命令兼容性**：`locks:update` 不保留无写入兼容别名。根 `check` 是唯一负责 staging 状态生成与模板检查的入口，避免“update”名称暗示会保存结果。

## 2026-08-06：首次 `apply-template` 合同

- **仓库地址**：默认硬编码为用户确认的 `https://github.com/YewFence/template.git`，同时保留 `--repo` 覆盖本地 fixture、私有仓库或其他 Git 服务；`--ref` 必须显式提供 tag、完整 commit、branch 或本地 `HEAD`，不再默认 `main`。
- **获取方式**：应用器使用浅层 sparse checkout，只展开 `tools/template-tool`、根 launcher 和选定的 `templates/<name>`；认证完全交给 Git，不读取或记录 token。
- **应用语义**：从模板 subtree 建立无父提交的临时 commit，先按 `[apply].protected` 排除根级身份与工作区控制文件，再对目标仓库执行 Git 原生 squash merge。成功只留下 staged changes，不移动分支、不创建提交。
- **冲突语义**：有冲突时返回非零并保留 index stages 与工作树，不创建 `MERGE_HEAD`；非冲突型 merge 错误自动 `git reset --hard HEAD`，因为入口已证明 tracked、staged 和普通 untracked 状态均为空。
- **Jujutsu**：允许 detached HEAD 和 colocated `.jj` 仓库，但只操作 Git index/工作树；输出提醒先完成、解决或取消本次应用，再继续普通 jj 操作。
- **版本边界**：`v0.1.0` 只承诺首次 apply，不保存 provenance 状态，不把重复 apply 描述为模板升级协议。

## 2026-08-06：模板 `ci.yml` 收敛

- **Module interface**：shared workflow layout 只暴露 `project_cache` 可选 slot；触发器、权限、并发、job 拓扑、mise 安装、pnpm 文档缓存和稳定任务调用全部隐藏在 module 实现中。
- **触发器**：统一为 `pull_request(main)` 与手动触发；移除 Rust 独有的 `push(main)`，避免同一提交在 push 与后续 PR 路径重复跑完整 CI。release 与部署仍由各自 workflow 负责。
- **任务调用**：项目检查统一调用 `mise run check`，在线 action 策略调用 `mise -E ci run actions:versions:check`；不再在 workflow 复制各模板的项目内部任务组合，审计则由独立 `audit.yml` 拥有。
- **锁预检**：check job 直接执行 `mise -E ci install --dry-run --locked`，验证基础与 CI 环境锁文件完整性；这是 workflow 启动基础设施，不包装成项目任务。
- **缓存 adapter**：Go 保留 build/module 缓存，Rust 保留 rust-cache；三个模板共用的 pnpm store 缓存由 shared 直接拥有，不再通过 overlay slot 注入。
- **Action 版本漂移**：公共 workflow 采用仓库现有模板中较新的已固定引用：checkout `v7.0.1`、mise-action `v4.2.3`，Go/Rust 缓存 action 保留各自现有固定版本。
- **Rust job 合并**：Rust 的 repository、language check 和 test job 合并为稳定 `check` 接口。取舍是失去三块独立 job 状态，但换来 workflow 不理解项目内部任务拆分；mise 任务仍保留并行组合与本地可复现性。

## 2026-08-06：Renovate 结构化配置

- **Module interface**：Renovate module 的调用方只选择一个 JSON profile；module 固定读取 `shared/renovate/base.json`，拒绝 base/profile 对普通顶层键的重复归属，并把双方 `packageRules` 按 base 后 profile 的顺序追加。
- **公共所有权**：schema、recommended presets、时区、dashboard、最小发布时间、lock maintenance，以及 GitHub Actions/npm/mise/major 更新规则归 base 所有。Go 原来仅有措辞差异的 npm 规则采用 common/Rust 的中性描述。
- **模板 adapter**：profile 只拥有 `enabledManagers` 与真实语言规则；Go 保留 gomod tidy 和 Go toolchain 两类规则，Rust 保留 Cargo 分组，common 不增加语言规则。
- **规则顺序**：公共规则始终先于语言规则，使 Go 的具体 toolchain 规则可以覆盖较通用的 mise 分组字段；Rust Cargo 规则移到公共规则之后，但匹配 manager 不重叠，不改变行为。
- **根仓库 profile**：旧实现扫描 `shared/**` 与 `overlays/**`；新责任域把根 Renovate 限定为 monorepo 自身环境，只维护根 workflow、根 mise 状态和 `tools/**` 等维护依赖，不自动更新模板蓝图的兼容版本线。
- **模板维护策略**：`shared/**`、`overlays/**` 和 `templates/**` 中的模板依赖声明由维护者人工调整。生成项目自带的 Renovate 配置继续启用语言 manager、Action digest pinning 和 lockfile maintenance，负责用户项目引导后的日常更新。
- **序列化**：最终配置统一使用稳定的 UTF-8、两空格缩进和末尾换行；模板和根配置都由同一 module 生成并纳入 `sync:check`。

## 2026-08-06：monorepo 根 CI

- **所有权**：根 `.github/workflows/ci.yml` 是维护仓库自身基础设施，直接维护且不参与 shared/template render，避免生成器的 CI 依赖生成器输出形成循环。
- **job 拓扑**：`source` job 验证根生成同步和 template-tool 本地 Git 集成测试；common、Go、Rust 分别使用独立 job、失败状态和缓存，不做第一版路径影响分析。
- **模板环境**：旧实现先消费模板自己的锁文件；新合同由根级 `mise run check <name>` 创建 staging，并通过 overlay validation adapter 生成临时锁定状态后检查。
- **缓存**：Go job 缓存 build/module，Rust job 使用 rust-cache，common 只使用 mise-action 缓存；缓存键不能再依赖模板快照中不存在的锁文件。
- **根 Renovate**：monorepo profile 增加 `.github/**` 扫描路径，使根 workflow 的固定 action 引用由根配置维护；`templates/**` 仍被忽略。

## 2026-08-06：根级 `actions:update`

- **输入集合**：旧实现发现根、shared 和 overlay workflow 来源；新责任域要求模板来源保留兼容版本线，因此根级更新器只固定 `.github/workflows/**` 的 monorepo 维护 workflow。
- **工具所有权**：根 mise 声明 `pinact = "4"`，统一使用三天最小发布时间并允许从 `MISE_GITHUB_TOKEN` 注入可隐藏的 API token；不依赖任一模板的工具环境。
- **执行方式**：删除 Python actions updater、专用 CLI 和事务测试；根 `actions:update` 直接运行 `pinact run --update .github/workflows`。普通 Git diff 负责审查和撤销，不再维护只服务少量根 workflow 的复制/回滚抽象。
- **模板隔离**：shared、overlay 和模板快照不参与根 digest 更新；validation adapter 调用的是 staging 模板自己的 `actions:update`。

## 2026-08-06：模板 `docs.yml` 收敛

- **Module interface**：shared docs workflow 不再暴露 slot；触发器、Pages 构建/部署拓扑、artifact 路径、文档工具安装、pnpm store 缓存、稳定 `mise run docs:build` 调用和 action 引用全部由公共实现拥有。
- **工具选择**：三份模板统一声明 pnpm，并在 workflow 中只安装文档构建需要的 `node pnpm`；文档任务统一使用 `pnpm install --frozen-lockfile` 与 `pnpm run`，overlay 不再表达包管理器差异。
- **缓存所有权**：独立部署 workflow 与 CI docs job 都直接使用 shared pnpm store 缓存实现，不再为相同行为保留 overlay adapter。
- **权限**：采用 common/Rust 的最小 job-level 权限：build 仅 `contents: read`、`pages: read`，deploy 仅 `pages: write`、`id-token: write`；移除 Go 原有 workflow-level 写权限，防止 build job 获得不需要的 Pages 写入和 OIDC 权限。
- **checkout ref**：统一显式 checkout `main`。push 触发行为不变；手动触发时也始终部署主分支文档，避免从任意临时 ref 覆盖正式 Pages。

## 2026-08-06：模板 `prepare-release.yml` 收敛

- **Module interface**：shared workflow 只暴露 `release_install_args`、`release_files` 和可选 `release_files_update` 三个 slot；触发器、权限、release notes 判定、release 分支、PR 创建/更新和摘要输出全部由公共实现拥有。
- **版本计算**：三模板统一调用 `release:version` 与 `release:tag`，并把 version、tag 和 checkout 后的 `git rev-parse HEAD` 作为 step output。选择实际 HEAD 而不是 Go 原有的 `${{ github.sha }}`，保证 release PR 元数据描述的是 workflow 真正处理的提交。
- **受管文件**：common/Go adapter 只声明 `CHANGELOG.md`，Rust 声明 `CHANGELOG.md`、`Cargo.toml`、`Cargo.lock`；公共实现用 Bash 数组完成变更检查和精确暂存，不把静态文件列表复制到整段分支逻辑。
- **Rust 更新**：Rust 独有 adapter 安装 `cargo-edit` 并调用 `release:version:update`，common/Go 仅安装 `git-cliff` 且不绑定更新步骤。Cargo 版本与 lockfile 是真实语言差异，保留在 seam 后面。
- **摘要措辞**：统一使用中性的 `Release files changed`，替代 common/Go 的 `Changelog changed`，使公共输出准确覆盖所有模板而不暴露语言条件分支。

## 2026-08-06：模板 `release.yml` 收敛

- **Module interface**：shared release workflow 拥有触发器、最小权限、version/release/关闭旧 PR 三个公共 job，只暴露完整 `build_job`、`release_needs`、可选 `release_artifact_download` 与 `release_files` 四个 slot。Go/Rust 平台矩阵与打包步骤作为大 adapter 保持完整，不把矩阵字段拆成大量浅层 slot。
- **common 行为**：common 不绑定 build 或资产 slot，release 仅依赖 version，继续发布无附件的 GitHub Release；不为接口整齐而新增无意义的 placeholder build job。
- **权限**：统一采用 workflow-level `contents: read`，仅 release job 提升为 `contents: write`。这修正 Go 原有的全 workflow 写权限，使 version 与 build job 没有不必要的仓库写入能力。
- **版本输出与校验**：version job 对三模板统一输出去掉 `v` 的 version，并对所有事件路径得到的 tag 执行同一 semver 形状校验；Go build 继续从公共 version output 注入构建版本。
- **资产顺序**：Go/Rust 先下载并验证 build artifacts，再创建缺失的 release tag，随后附加 `dist/*` 发布。选择 Rust 原有的前置下载语义，避免 artifacts 缺失时先推送一个没有对应 Release 的孤立 tag。
- **语言 adapter**：Go 保留五组 GOOS/GOARCH、Go 缓存、build 与 tar/zip 打包；Rust 保留五组 target、cross compiler、linker、rust-cache 与 tar.gz 打包。两者只共享发布协议，不伪造统一构建模型。

## 2026-08-06：模板 `audit.yml` 收敛

- **Shared workflow**：三份模板统一使用独立的 shared `audit.yml`，`ci.yml` 不再包含 audit job；公共实现拥有权限、并发、job 步骤与稳定的 `mise -E ci run audit` 入口，只暴露审计路径、最小工具安装参数和缓存三个 adapter slot。
- **触发职责**：统一支持默认分支 push、面向默认分支的 pull request、每周一 schedule 与手动触发。push/PR 只在依赖清单、锁文件、mise 配置或 audit workflow 变化时运行；定时任务不受路径过滤影响，继续发现上游新披露的漏洞。
- **语言 adapter**：Go 只安装 Go 与 govulncheck，并缓存 build/module；Rust 只安装 cargo-audit，并保留 rust-cache。common 的 audit 仍是明确 placeholder，只在 mise 与 audit workflow 来源变化时运行，采用完整环境安装且不伪造语言依赖路径。

## 2026-08-06：模板检查不写 `.git` 标记

- **问题**：原实现把指向临时 bare repository 的 `.git` 文件写入 `templates/<name>`，正常异常由 `finally` 清理，但 SIGTERM/SIGKILL 可能让生成快照遗留额外路径。
- **取舍**：检查子进程直接继承临时 `GIT_DIR`、`GIT_WORK_TREE` 和 `GIT_INDEX_FILE`；Git 命令仍看到完整 repository 与 baseline index，正式模板目录从始至终不创建 `.git`。baseline 使用普通 `git add --all`，尊重模板 `.gitignore`，不把 Cargo/Go/Node 缓存伪装成 tracked 文件。
- **旧实现缺陷**：原 `.git` 标记只指向临时 Git dir，没有把独立 `GIT_INDEX_FILE` 传给 mise 子进程，导致 `git grep` 类任务没有检查到完整 baseline；markerless 实现同时修正了这条隐蔽的空检查路径。
- **嵌套 Git**：需要自行创建临时仓库的测试必须在完整测试生命周期内显式移除父级 `GIT_DIR`、`GIT_WORK_TREE` 和 `GIT_INDEX_FILE`，并在 cleanup 恢复原值；单条 Git helper 也过滤这些变量。Go 初始化测试采用该规则，避免临时 `git init`、被测 reset 逻辑、commit 和 hook 误操作外层 baseline repository。
- **验证**：受控集成测试在假 mise 进程内同时断言 Git worktree 可用、`.git` 路径不存在、忽略缓存不在 index 且 index/worktree 无差异；三个模板的真实检查继续覆盖 Git-based newline/leak 任务和 Go 嵌套仓库测试。强制终止最多遗留系统临时目录，不再污染受管模板快照。

## 2026-08-06：生成模板根目录权限

- **问题**：renderer 的 staging 根来自 `tempfile.mkdtemp`，默认 mode 为 `0700`；整体 rename 后该 mode 会成为 `templates/<name>` 的实际目录权限，使不同 UID 的容器化验证工具无法遍历模板内容。
- **取舍**：staging 根创建后立即固定为 `0755`，子目录继续遵循普通目录创建语义；Git 不跟踪目录 mode，`sync:check` 仍按既定合同不比较目录权限，但本地 render 结果保证可遍历。
- **验证**：renderer 集成测试断言最终模板根为 `0755`；官方 Renovate 容器继续使用只读 bind mount 和自身非 root 用户验证四份配置，不通过 `--user` 绕过权限问题。
- **官方结果**：固定的 `renovate/renovate:44.13.2` 镜像在 `--network none`、repository read-only bind mount 下运行 `renovate-config-validator --strict --no-global`，根配置与三个模板配置全部验证成功。

## 2026-08-06：新项目 `init-project` 合同

- **独立入口**：`apply-template` 继续只接受至少一个 commit 的已有仓库，不根据仓库状态隐式切换模式；`init-project` 专门实现 `mkdir`、`git init` 之后的新项目 bootstrap，并复用同一 sparse fetch 与 squash apply 内核，但不复用已有项目的 protected denylist。
- **目标边界**：初始化目标必须是干净、unborn 且参数路径就是 Git repository root 的仓库；已有历史明确提示改用 `apply-template`，untracked 内容、嵌套目录或进行中的 Git 操作直接失败。
- **首个提交**：入口使用普通 `git commit --allow-empty` 创建消息为 `chore: initialize repository` 的用户提交，不使用 `--no-verify`，不绕过用户 identity、签名或 hook 策略；应用成功后模板内容保持 staged，HEAD 仍指向该无父根提交。
- **失败语义**：初始提交创建失败时不进入 apply；创建成功后的获取或非冲突应用错误保留干净的初始提交并报告其 SHA，冲突语义继续由 `apply-template` 保留 index stages 和恢复提示。入口不猜项目名称、不初始化远端，也不替用户提交模板内容。

## 2026-08-06：项目实例化归外部工具所有

- **现状问题**：Go 模板通过生成项目内的 `mise run init` 和 `tools/init-template` 完成项目身份、module path、README 与 AGENTS 替换，Rust 和 common 则依靠人工替换；同一种一次性实例化责任存在三套不对称流程。
- **责任边界**：项目名称、描述、GitHub owner、仓库名以及语言专属 module、crate 或 binary 身份的首次物化归 `template-tool`。模板交付物不再携带需要执行后删除的一次性初始化任务或工具。
- **入口语义**：`init-project` 面向干净的新仓库，自动执行完整项目实例化，再把实例化后的模板树作为 staged changes 应用；metadata 参数和交互行为由本节后续合同固定。
- **已有项目安全边界**：`apply-template` 继续面向已有历史的仓库，只执行纯 staged apply，不自动重写已有项目的名称、module、crate、remote 或 Git 历史。两个入口共享外部工具包和底层应用能力，但不伪造相同的自动初始化语义。
- **已有项目 token 语义**：`apply-template` 不接受 metadata，也不替换内容或路径 token；合法蓝图 token 可以保留在 staged changes 中，不导致应用失败。成功输出必须提示结果仍未实例化，并建议用 Git diff、status 和 uppercase token 搜索逐项审查；用户负责结合现有项目布局重命名、替换或删除。
- **Metadata 输入合同**：显式 CLI options 是 `init-project` 唯一稳定、可脚本化的正式接口。连接交互式终端时，工具可以提示补齐未提供的必填项；非交互环境缺少必填项必须直接失败。提示文本不属于兼容 API，工具不从 Git remote 猜测项目身份。
- **Metadata schema**：共享必填字段为 `--project-name`、`--description`、`--github-owner` 和 `--repo-name`。Go CLI profile 额外要求 `--go-module` 与 `--binary-name`；Rust profile 额外要求 `--cargo-package` 与 `--binary-name`；common 不增加语言字段。显示名称、仓库身份和语言标识符保持分离，不用单个模糊 `name` 隐藏差异。
- **单 README 合同**：每个 overlay 的模板蓝图只保留一个带 metadata 占位符的 `README.md`，不再维护“模板使用指南 `README.md` + 项目内容 `README.template.md`”双文件协议。`init-project` 在临时树中直接原地实例化该 README；`apply-template` 不对它做自动实例化或特殊消费，只按普通模板文件交给 Git 应用与用户审查。
- **一次性 Go 入口**：从蓝图直接删除 `tools/init-template`、`tools/apply-existing` 和 `[tasks.init]`，不保留兼容入口。原 README 中的统一使用、自举和应用器说明迁到根 README；overlay README 只保留模板特有功能介绍。
- **文档归属**：根 `README.md` 是所有模板共用的外部使用入口，统一说明 `apply-template`、`init-project`、metadata 参数和依赖引导；每个 overlay 的项目 `README.md` 只介绍该模板特有的功能、结构和语言行为，不复制应用器操作流程。
- **单 AGENTS 合同**：每个 overlay 的模板蓝图只保留一个带项目规则的 `AGENTS.md`，由 `init-project` 在临时树中原地实例化。原来只服务模板维护者的 `AGENTS.md` 内容迁出用户交付物；`apply-template` 继续把 `AGENTS*` 当作已有项目的受保护路径，不自动消费或覆盖它。
- **新项目 protected policy**：`init-project` 的目标已证明是干净、unborn 且没有 untracked 内容的新仓库，因此完整应用实例化后的模板文件，包括 `README.md`、`AGENTS.md`、`.gitignore`、许可证和 notice；已有项目的 denylist 只属于 `apply-template`。
- **取代关系**：本决策取代“Go 在工具安装后运行生成项目内 `mise run init`”的旧顺序；依赖引导发生在项目实例化完成之后。
