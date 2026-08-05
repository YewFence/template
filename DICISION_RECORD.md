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
