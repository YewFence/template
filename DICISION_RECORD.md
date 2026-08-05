# 决策记录

## 2026-08-06：首批 `mise.ci.toml` 收敛

- **范围**：三份模板的 CI/维护环境配置、shared layout、overlay adapter fragment，以及生成配置绑定。
- **取舍**：公共 release helper 和在线 action 版本检查原样迁移到 shared layout；模板差异只通过 `maintenance_tools`、`audit_tasks`、`release_version_tasks` 和 `release_package` 四个语义 slot 注入。
- **理由**：现有三份 release helper 的命令、输入和失败行为一致，继续复制会保留漂移源；Go、Rust 的工具和打包入口确实不同，不能靠文本合并隐藏差异。
- **聚合任务**：Go 的 `audit` 按 `mod:verify` 再 `vuln:check` 顺序执行，`actions:versions:check` 按 pin 检查再 outdated 检查执行，均使用 mise 任务数组保留 fail-fast 语义。
- **common 行为**：common 的审计和打包仍是明确的 `[PLACEHOLDER]` 成功任务，避免生成后的语言无关模板伪造安全结果或资产路径。
- **生成结果**：普通 `render` 只从 layout、fragment 和现有受管静态文件生成，不运行原生命令；三份 `mise.ci.toml` 快照随后由 renderer 重新物化。

## 2026-08-06：锁文件更新流程

- **配置合同**：`templates.toml` 只登记每个模板允许回写的 `locks.outputs`；命令名和语言命令由 `overlays/<name>/mise.toml` 的统一 adapter interface 拥有。
- **执行边界**：根工具先 render staging，再由 overlay adapter 调用一次 `mise -E ci lock`（可选 `--bump`）、模板专属 Go/Cargo 原生命令和 `aube install --lockfile-only`；普通 render 不隐式生成锁文件。
- **安全校验**：adapter 前后比较完整 staging 文件树，任何未声明路径变化都失败；每个声明输出必须是 staging 内的普通、不可执行文件，拒绝目录和 symlink。
- **回滚取舍**：验证通过后才把完整输出替换回对应 overlay 的 `static/`，随后重新 render、sync check 和模板项目 check；切换、渲染或检查失败时恢复原 overlay 与模板目录。目录 rename 覆盖正常错误和可处理中断，不承诺抵御 `SIGKILL` 或系统崩溃。
- **测试策略**：单测使用注入的假 adapter 覆盖允许输出、越界修改、symlink 输出和最终验证失败，真实 mise、Go、Cargo 与 aube 只由维护者主动运行的 `locks:update` 触发。

## 2026-08-06：首次 `apply-template` 合同

- **仓库地址**：默认硬编码为用户确认的 `https://github.com/YewFence/template.git`，同时保留 `--repo` 覆盖本地 fixture、私有仓库或其他 Git 服务；`--ref` 默认 `main`，严格复现时由调用者传 tag 或完整 commit。
- **获取方式**：应用器使用浅层 sparse checkout，只展开 `tools/template-tool`、根 launcher 和选定的 `templates/<name>`；认证完全交给 Git，不读取或记录 token。
- **应用语义**：从模板 subtree 建立无父提交的临时 commit，先按 `[apply].protected` 排除根级身份与工作区控制文件，再对目标仓库执行 Git 原生 squash merge。成功只留下 staged changes，不移动分支、不创建提交。
- **冲突语义**：有冲突时返回非零并保留 index stages 与工作树，不创建 `MERGE_HEAD`；非冲突型 merge 错误自动 `git reset --hard HEAD`，因为入口已证明 tracked、staged 和普通 untracked 状态均为空。
- **Jujutsu**：允许 detached HEAD 和 colocated `.jj` 仓库，但只操作 Git index/工作树；输出提醒先完成、解决或取消本次应用，再继续普通 jj 操作。
- **版本边界**：`v0.1.0` 只承诺首次 apply，不保存 provenance 状态，不把重复 apply 描述为模板升级协议。

## 2026-08-06：模板 `ci.yml` 收敛

- **Module interface**：shared workflow layout 只暴露 `project_cache`、`audit_cache`、`docs_cache` 三个可选 slot；触发器、权限、并发、job 拓扑、mise 安装和稳定任务调用全部隐藏在 module 实现中。
- **触发器**：统一为 `pull_request(main)` 与手动触发；移除 Rust 独有的 `push(main)`，避免同一提交在 push 与后续 PR 路径重复跑完整 CI。release 与部署仍由各自 workflow 负责。
- **任务调用**：项目检查统一调用 `mise run check`，审计调用 `mise -E ci run audit`，在线 action 策略调用 `mise -E ci run actions:versions:check`；不再在 workflow 复制 Go 的 `mod:verify`/`vuln:check` 或 Rust 的 `repo:check`/`rust:check`/`test` 组合。
- **锁预检**：check job 直接执行 `mise -E ci install --dry-run --locked`，验证基础与 CI 环境锁文件完整性；这是 workflow 启动基础设施，不包装成项目任务。
- **缓存 adapter**：Go 保留 build/module 与 pnpm store 缓存，Rust 保留 rust-cache；common 不绑定 cache slot。缓存是模板真实性能差异，不提升到 shared。
- **Action 版本漂移**：公共 workflow 采用仓库现有模板中较新的已固定引用：checkout `v7.0.1`、mise-action `v4.2.3`，Go/Rust 缓存 action 保留各自现有固定版本。
- **Rust job 合并**：Rust 的 repository、language check 和 test job 合并为稳定 `check` 接口。取舍是失去三块独立 job 状态，但换来 workflow 不理解项目内部任务拆分；mise 任务仍保留并行组合与本地可复现性。

## 2026-08-06：Renovate 结构化配置

- **Module interface**：Renovate module 的调用方只选择一个 JSON profile；module 固定读取 `shared/renovate/base.json`，拒绝 base/profile 对普通顶层键的重复归属，并把双方 `packageRules` 按 base 后 profile 的顺序追加。
- **公共所有权**：schema、recommended presets、时区、dashboard、最小发布时间、lock maintenance，以及 GitHub Actions/npm/mise/major 更新规则归 base 所有。Go 原来仅有措辞差异的 npm 规则采用 common/Rust 的中性描述。
- **模板 adapter**：profile 只拥有 `enabledManagers` 与真实语言规则；Go 保留 gomod tidy 和 Go toolchain 两类规则，Rust 保留 Cargo 分组，common 不增加语言规则。
- **规则顺序**：公共规则始终先于语言规则，使 Go 的具体 toolchain 规则可以覆盖较通用的 mise 分组字段；Rust Cargo 规则移到公共规则之后，但匹配 manager 不重叠，不改变行为。
- **根仓库 profile**：根 `renovate.json` 扫描根 mise/工具、`shared/**`、`config/**` 与 `overlays/**`，启用三模板 manager 并明确忽略 `templates/**` 生成快照。生成输出因此不会成为第二个依赖更新来源。
- **序列化**：最终配置统一使用稳定的 UTF-8、两空格缩进和末尾换行；模板和根配置都由同一 module 生成并纳入 `sync:check`。

## 2026-08-06：monorepo 根 CI

- **所有权**：根 `.github/workflows/ci.yml` 是维护仓库自身基础设施，直接维护且不参与 shared/template render，避免生成器的 CI 依赖生成器输出形成循环。
- **job 拓扑**：`source` job 验证根生成同步和 template-tool 本地 Git 集成测试；common、Go、Rust 分别使用独立 job、失败状态和缓存，不做第一版路径影响分析。
- **模板环境**：每个模板 job 先用模板自己的锁文件执行 `mise -C templates/<name> install --locked`，并设置 ceiling、禁用全局配置、临时信任模板路径；随后调用根级 `mise run check <name>`。
- **缓存**：Go job 缓存 build/module，Rust job 使用 rust-cache，common 只使用 mise-action 缓存。缓存 key 包含模板锁或语言校验文件，不跨模板共享语言缓存。
- **根 Renovate**：monorepo profile 增加 `.github/**` 扫描路径，使根 workflow 的固定 action 引用由根配置维护；`templates/**` 仍被忽略。

## 2026-08-06：根级 `actions:update`

- **输入集合**：只发现根 `.github/workflows/**`、`shared/**` 和 `overlays/**` 中的 workflow/action YAML 与 Jinja fragment；绝不把 `templates/**` 生成快照交给 pinact。
- **工具所有权**：根 mise 声明 `pinact = "4"`，统一使用三天最小发布时间并允许从 `MISE_GITHUB_TOKEN` 注入可隐藏的 API token；不依赖任一模板的工具环境。
- **事务流程**：先把显式来源复制到临时目录，pinact 只能修改现有普通文件；成功后才回写来源、重新生成根配置和三份模板，并执行同步检查。
- **失败语义**：pinact 创建/删除文件、输出 symlink、render 或同步检查失败时，恢复调用前全部来源并重新生成旧快照，不留下只更新一侧的状态。
