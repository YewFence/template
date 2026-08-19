# Codecov 上传 capability 设计

## 状态

设计完成，待实现和验证。本文描述 `common`、`go-cli` 和 `rust` 三个 template profile 的 `codecov-upload` template capability；实现完成后由 GitHub Actions 执行完整 staging validation，本地不要求运行完整 `mise run check`。

## 背景

Codecov 上传本身是语言无关的 CI 行为，但覆盖率报告的生成命令、工具链和报告格式属于项目 profile。模板应该把 Codecov 接线、权限和失败语义稳定下来，同时让每个 profile 通过一个很小的 coverage task interface 提供自己的报告生成 adapter。

`common` 不知道项目最终使用哪种语言，因此不能生成真实覆盖率报告；这不妨碍它提供 Codecov capability。启用后，`common` 交付的是明确的 coverage task 占位 adapter 和完整上传 workflow，使用者只需要替换该 task，而不需要重写 Codecov 认证、fork PR 和上传步骤。

## 设计决策

### 三个 profile 都声明 capability

在三个 profile 的 capabilities 表中声明：

```toml
codecov-upload = false
```

默认关闭，用户在选择 template capability 时自行启用。该 capability 与容器镜像发布、文档站点和 crates.io 发布独立存在。关闭 capability 时不保留半套 Codecov workflow、工具或忽略规则。

### 上传模块和 coverage adapter 分离

`codecov-upload` 的深模块接口只有一个稳定任务：

```text
mise run coverage
```

这个 task 的唯一外部合同是：在当前工作树生成恰好一个 Codecov 支持的报告文件，并以确定的相对路径供上传 job 使用。Go 和 Rust 提供真实 adapter，`common` 提供可替换的占位 adapter。`mise run coverage` 不安装或调用 Codecov uploader，也不负责认证、PR 识别、上传或覆盖率策略。

Codecov Action 仍然拥有 Codecov 上传协议和 GitHub 集成，包括事件上下文识别、PR 关联、OIDC 接线和上传失败传播。mise 拥有 Codecov CLI 的安装、版本解析和锁定，并把已安装 executable 通过 Action 的 `binary` input 提供给 Action；设置 `binary` 后 Action 自身的 CLI integrity check 会被绕过，这是有意的所有权转移，由 bootstrapped project 的 mise lock 和校验承担供应链完整性。

这种拆分避免把 Go 的 `-coverprofile`、Rust 的 `cargo llvm-cov`、Codecov CLI 参数或用户未来选择的其他工具暴露成 template CLI 参数；调用者只需要知道 `mise run coverage` 和报告路径，维护者可以在 overlay 内替换实现。

### PR tokenless 上传与默认分支 OIDC 分离

模板默认面向 public repository。Pull request coverage 使用普通 `pull_request` 触发器和 Codecov 的 tokenless 路径，job 只授予 `contents: read`，不授予 `id-token: write`，也不读取 `CODECOV_TOKEN`。workflow 不使用 `pull_request_target`，避免让不受信任的 PR 代码进入拥有 secrets、OIDC 或写权限的上下文。

启用 capability 的 public repository 必须在 Codecov 组织设置中允许 tokenless upload。Fork PR 无 token 时由 Codecov Action 自动检测 fork、设置 head branch、commit 和 PR 上下文并进入 tokenless 路径；同仓库 PR 的无 token 上传依赖组织级 tokenless 设置。模板不设置 `override_branch` 或 `override_pr`，因为这些 input 只用于覆盖已有 CI event metadata，不属于当前 template interface。未满足 Codecov 组织设置时，上传按 `fail_ci_if_error: true` 失败，不静默降级。

默认分支 coverage 使用独立的可信上传边界，在 `push` 到 `main` 时运行，并提供 `workflow_dispatch` 人工入口。手动触发的 job 必须用 `github.ref == 'refs/heads/main'` 拒绝非默认分支 ref。该 job 授予 `contents: read` 与 `id-token: write`，重新生成 coverage report，再由 Codecov Action 使用 OIDC 上传，不消费 PR workflow 产生的 artifact。

模板不为使用者创建长期 `CODECOV_TOKEN`。Private repository 不属于默认 capability 合同，因为其上传需要额外认证；使用者必须在生成项目中自行选择 Codecov secret、组织策略或其他认证方式，并相应修改 workflow。文档必须明确指出 public repository 假设和 private repository 自定义边界。

### Action 与 Codecov CLI 版本所有权

Template deliverable 声明 Codecov Action 的 major compatibility line `codecov/codecov-action@v7`；bootstrapped project 继续通过现有 pinact 流程把 Action 引用固定到 commit digest。模板不声明 Action 的 minor 或 patch tag。

Codecov CLI 作为 capability-owned CI tool 由 mise 的 `pipx:codecov-cli` backend 管理，初始 compatibility line 为 `11`。共享 `shared:mise/ci/codecov-tools.toml.j2` fragment 拥有该声明，三个 profile 都通过 `mise.ci.toml` 的 `coverage_tools` slot 在 capability 启用时绑定它；Rust 在同一 binding 中继续组合 profile-owned `cargo-llvm-cov` fragment。普通 `mise.toml` 不声明 Codecov CLI，因为本地 `mise run coverage` 不调用 uploader。Bootstrapped project 通过 mise 原生命令生成并提交精确锁定状态；workflow 不让 Codecov Action 自行选择或下载未受 mise 锁定的 CLI。该设计信任 mise 的原生工具解析、锁定和校验合同，不为 `pipx` backend 增加 capability 专属的重复校验。

Coverage workflow 使用带固定 `id` 的准备步骤运行 `mise which codecovcli`，把返回的绝对 executable path 写入 `$GITHUB_OUTPUT`，再通过 Codecov Action 的 `binary` input 引用该 step output。设置 `binary` 后 Action 跳过自身的 CLI 下载和 integrity check，这是有意的所有权转移。Action 仍然负责上传和 GitHub 集成，mise 只负责提供经过版本解析与锁定的 CLI；不新增自制 `codecov:upload` task，也不把 Codecov 上传命令复制进 workflow 或 mise task。

### 上传失败阻断 coverage job

上传步骤使用 `fail_ci_if_error: true`。coverage job 失败时，CI 会明确显示报告生成或上传问题；报告缺失不能被当作“没有覆盖率”而静默通过。主检查 job 与 coverage job 分开，覆盖率失败不会改变现有 `check` task 的语言检查顺序，但 workflow 的总体结果仍然失败。

第一版不生成 `codecov.yml`，不替用户决定 patch/project threshold、flags、components 或 carryforward 策略。这些是项目质量策略，不是模板能力的必要合同。

## Profile adapters

### common

启用时在 `mise.toml` 增加：

```text
coverage
```

该 task 明确提示使用者把它替换为项目实际的覆盖率命令和报告路径。它不能生成伪造报告，也不能用当前的占位 `test` task 推断覆盖率。common validation 只验证 task、workflow 和报告路径合同，不声称未知语言的覆盖率实现已经可用；用户启用 capability 后必须在首次 CI 运行前完成这个占位 adapter。

### go-cli

Go adapter 使用标准库覆盖率能力，在仓库根目录生成 `coverage.out`：

```text
go test -covermode=atomic -coverprofile=coverage.out ./...
```

它不改变现有 `test` task，也不把覆盖率执行塞进主 `check` task。coverage job 单独调用 `mise run coverage`，然后将 `coverage.out` 明确交给 Codecov Action。

### rust

Rust adapter 在 `mise.ci.toml` 声明 `cargo-llvm-cov` 的兼容版本线，并在仓库根目录生成 `lcov.info`：

```text
cargo llvm-cov --workspace --all-features --lcov --output-path lcov.info --locked
```

具体工具安装参数和 Cargo cache 由 Rust overlay adapter 拥有。coverage task 不发布 crates.io，不修改 Cargo manifest，也不替代现有 `cargo test`、`cargo clippy` 或 package check。

报告文件命名是 adapter 与 uploader 之间的内部合同，不成为 project instantiation metadata。第一版固定为单个 `report` 路径；如果未来确实需要多个报告，届时显式修改 adapter interface 和 shared uploader 合同，不提前引入逗号分隔列表或自动搜索。

## Workflow 设计

### 触发器和 checkout

PR coverage 作为现有 `.github/workflows/ci.yml` 的 capability-owned job，并以 `if: github.event_name == 'pull_request'` 保证它只响应该 workflow 的 `pull_request` 事件。它 checkout 当前事件对应的提交，并在运行用户代码后执行 tokenless Codecov 上传，不在 `push` 或 `workflow_dispatch` 事件中运行。

默认分支 coverage 使用独立 `.github/workflows/coverage.yml`，接受 `push` 到 `main` 和 `workflow_dispatch`。Coverage job 以 `github.event_name == 'push' || github.ref == 'refs/heads/main'` 限制人工触发 ref，重新 checkout 默认分支内容、生成报告并使用 OIDC 上传。

两条路径都不使用 `pull_request_target`。默认分支 OIDC workflow 不下载或解析 PR workflow 生成的 artifact，从而避免把不可信 artifact 引入 privileged job。

### 权限

PR coverage job 使用最小权限：

```yaml
permissions:
  contents: read
```

默认分支 coverage job 使用：

```yaml
permissions:
  contents: read
  id-token: write
```

`id-token: write` 只存在于可信的默认分支上传 job，不提升 PR workflow，也不出现在执行 PR 可修改 coverage task 的 job。Codecov 上传不需要 `packages: write`、`contents: write` 或 `pull-requests: write`。

### Job 结构

Shared 来源拥有 PR 与默认分支 coverage 的安全和上传结构：触发条件、权限、checkout、mise、`mise which codecovcli`、Codecov Action 和失败摘要。Profile overlay 只提供一个完整 `coverage_adapter` fragment，负责 cache、生成报告，并以固定 step `id: coverage` 暴露 `report` 路径。

Renderer 不支持 fragment 内声明嵌套 slot，因此不为该 capability 扩展 renderer interface。`ci.yml` 的单个语义 `coverage_job` slot 按顺序绑定 shared PR job 前段、overlay `coverage_adapter` 和 shared PR job 后段；三段共同组成完整 job。独立 `coverage.yml` layout 直接声明 `coverage_adapter` slot。两个位置保持相同的 adapter 缩进合同并复用同一 overlay fragment。验证面向最终渲染 workflow，不把三段 fragment 的文件形状当成外部合同。

PR coverage job 至少包含：

1. checkout；
2. 使用现有 `jdx/mise-action` 安装 profile 需要的 CI tools 和 mise 管理的 Codecov CLI；
3. profile-specific cache（Go 使用 Go build/module cache，Rust 使用 Rust cache，common 不添加假 cache）；
4. profile `coverage_adapter`，其固定 step `id: coverage` 运行 `mise run coverage` 并暴露 `report` 路径；
5. 运行 `mise which codecovcli` 并通过 step output 暴露 executable 的绝对路径；
6. `codecov/codecov-action@v7` 通过 `binary` 使用该 executable，引用 `${{ steps.coverage.outputs.report }}`，不启用 OIDC，也不设置 `override_branch` 或 `override_pr`；
7. 失败摘要，确保缺失报告和 Codecov 错误能从 Actions 日志定位。

默认分支 coverage workflow 使用相同的 `coverage_adapter`、报告路径和 CLI 安装边界，但 Codecov Action 启用 OIDC，job 拥有 `id-token: write`，并设置 `group: coverage-${{ github.ref }}` 与 `cancel-in-progress: true`；触发器不包含 `pull_request`。

上传步骤应显式设置单个 `report` 文件并关闭无关的自动搜索，避免工作区中其他工具生成的文件被误上传。两个上传步骤都设置 `fail_ci_if_error: true`，由 Codecov 的上传结果直接决定 job 成败；workflow 不自行定义 coverage threshold、patch/project 策略或替代 Codecov status。外部 `binary` 不搭配 `skip_validation`：Action 保留默认的系统依赖检查，mise 负责 CLI 的版本解析、锁定和校验所有权。Action 只声明确切 major line 并沿用仓库的 pinact 流程；unbootstrapped template 不包含 Action digest 或 mise lock。

### mise 所有权

workflow 不复制 `go test`、`cargo llvm-cov`、用户自定义 coverage 命令或 Codecov CLI upload 命令。生成报告的行为只通过 `mise run coverage` 调用；Codecov Action 拥有上传和 GitHub 集成；mise 拥有 Codecov CLI tool declaration 和锁定。这个边界符合仓库关于“模板 workflow 只拥有触发器、权限、缓存、平台矩阵及 mise 启动基础设施”的自动化所有权规则。

## 来源和 slot 规划

| 来源 | 规划内容 |
| --- | --- |
| `templates.toml` | 三个 profile 声明 capability；PR CI、默认分支 coverage workflow、mise 和 `.gitignore` 的 conditional binding |
| `shared/layouts/.github/workflows/ci.yml.j2` | 保留单个语义 `coverage_job` slot；binding 组合 shared PR job 前段、overlay adapter 和 shared PR job 后段 |
| `shared/layouts/.github/workflows/coverage.yml.j2` | 拥有默认分支 OIDC coverage workflow 的稳定结构、`push`/`workflow_dispatch` 触发器、`main` ref guard、并发策略，并直接声明 `coverage_adapter` slot |
| `shared/layouts/mise.ci.toml.j2` | 使用现有语义 `coverage_tools` slot 接收 capability-owned CI 工具 |
| `shared/fragments/mise/ci/codecov-tools.toml.j2` | 统一声明 `"pipx:codecov-cli" = "11"`，供三个 profile 复用 |
| `overlays/*/fragments/mise/` | `coverage` task 和必要的 profile coverage 工具声明；Go/Rust 为真实 adapter，common 为明确失败的占位 adapter |
| `overlays/*/fragments/workflows/` | 单个完整 `coverage_adapter`，包括 profile cache、报告生成 task 和固定 `report` output；由 PR 与默认分支 workflow 复用，不重复上传、权限或认证实现 |
| `shared/fragments/workflows/coverage/` | PR job 前段与后段；拥有共享安全、CLI 接线、上传和失败摘要，不声明嵌套 slot |
| `shared/fragments/docs-ignored-paths.j2` 或 profile overlay | 忽略 `coverage.out`、`lcov.info`、`coverage.xml` 等 capability 生成的临时报告 |
| `overlays/*/mise.toml` | 按 enabled capability 检查任务、工具、workflow 和关闭时的缺席 |

是否把 Codecov badge 加入 README 不属于上传 capability 的必要输出。第一版不生成 badge，避免把 Codecov project visibility、默认 branch 和 README 文案耦合到上传合同；未来如果确有稳定需求，可以单独增加 capability-owned README fragment。

面向使用者的稳定认证、引导和 `common` adapter 合同由 monorepo 的 `docs/guides/codecov-upload.md` 统一拥有。它不作为 capability-owned README fragment 渲染进生成项目；根文档索引、根 README 和三个 overlay README 链接该指南。生成项目只保留 workflow 与 `mise run coverage` 合同，不复制维护指南全文。

## 验证合同

三个 validation adapter 都需要展开 `codecov-upload` 的启用和关闭状态。

启用时：

- `mise` task 列表含 `coverage`；
- `mise.ci.toml` 含来自 shared fragment 的 capability-owned `"pipx:codecov-cli" = "11"` tool declaration；普通 `mise.toml` 不含 Codecov CLI；
- Rust 的 `coverage_tools` binding 同时组合 shared Codecov CLI 与 overlay `cargo-llvm-cov`，Go 和 common 不伪造语言 coverage tool；
- `.github/workflows/ci.yml` 含 coverage job；
- PR coverage job 含 `if: github.event_name == 'pull_request'`，在 CI workflow 的 `push` 和 `workflow_dispatch` 事件中跳过；
- `coverage_adapter` 以固定 `coverage` step 调用 `mise run coverage` 并输出 `report`，不在 shared workflow 中复制 profile 命令；
- PR coverage job 权限只含 `contents: read`，不含 `id-token: write` 或 Codecov secret；
- PR Codecov Action 依赖 GitHub event 自动识别，不设置 `override_branch` 或 `override_pr`；public repository 使用说明明确要求在 Codecov 组织中允许 tokenless upload；
- 独立默认分支 coverage workflow 接受 `push` 到 `main` 和 `workflow_dispatch`，不接受 `pull_request`；人工触发时只允许 `github.ref == 'refs/heads/main'`；
- 默认分支 coverage job 含 `contents: read` 与 `id-token: write`，并启用 OIDC；
- 两条路径都复用同一个 `coverage_adapter` 和 `mise which codecovcli` step output，向 `binary` 传入绝对 executable path；上传步骤引用 `steps.coverage.outputs.report`；
- 两条上传步骤不设置 `skip_validation`，保留 Codecov Action 默认的系统依赖检查；
- renderer 不需要支持 fragment 内嵌套 slot；PR `coverage_job` 的三段 binding 和默认分支 layout 的直接 adapter slot 都渲染为结构完整的 workflow；
- Action 引用为 `codecov/codecov-action@v7`，bootstrapped project 的 pinact 流程负责 digest；
- 两条上传路径都含 `fail_ci_if_error: true`；
- 对应报告路径被 `.gitignore` 忽略；
- Go/Rust 的必要工具只存在于启用分支，common 不伪造语言工具。

关闭时：

- `coverage` task、PR coverage job、默认分支 coverage workflow、Codecov CLI tool、Codecov Action 和 capability-owned ignore paths 均不存在；
- 现有主 CI check、audit、release 和 docs job 不改变行为；
- 不残留 `id-token: write` 或 Codecov 相关 secret 引用。

验证不会向 Codecov 上传真实报告，也不会依赖外部 Codecov project。Go 和 Rust adapter 可以在 disposable staging 中运行本地覆盖率生成来验证报告文件；common 只做结构合同检查，因为它的 coverage task 本来就是由使用者替换的占位实现。完整 capability 矩阵由 GitHub Actions 运行，不要求本地执行 `mise run check`。

Renderer 合同、静态 workflow 合同、报告生成和完整 staging matrix 构成本仓库实现完成的验证门槛。真实 Codecov 服务端的 tokenless 策略、OIDC、commit/PR 关联及 status/comment 在首个启用 capability 的真实 public repository 中验收；该 live 验收不阻断本仓库实现完成，也不通过 `dry_run` 冒充服务端集成验证。

## 使用者自定义边界

启用 capability 后，使用者需要为 `common` 替换 coverage task；Go 和 Rust 通常可以直接使用模板提供的 adapter。默认合同假设 public repository，且使用者已在 Codecov 组织设置中允许 tokenless upload：PR 走无 token 上传，默认分支走 OIDC。Private repository 使用者必须自行提供适合其 Codecov 策略的认证方式。所有 profile 都可以在生成项目中替换覆盖率工具、报告格式、Codecov token/OIDC 配置、flags 和质量阈值，但这些修改属于项目自己的 workflow 和 mise 实现，不再由模板工具解释或实例化。

模板不为用户创建 `CODECOV_TOKEN` metadata 字段，也不把报告格式、测试包选择或阈值写入 `templates.toml`。这些内容若进入 profile 合同，会让一个通用上传能力变成按语言和项目策略不断膨胀的浅模块。

## 非目标

- 为 common 猜测或选择覆盖率生成器。
- 修改主 `test` 或 `check` task，使每次本地检查都必须生成覆盖率。
- 生成 `codecov.yml`、threshold、flags、components 或 badge。
- 使用长期 Codecov secret 作为默认认证方式。
- 上传 fork PR 的 secrets，或使用 `pull_request_target` 执行不受信任代码。
- 为 PR 默认设置 `override_branch` 或 `override_pr`，替代 Codecov Action 的 GitHub event 自动识别。
- 自制 Codecov 上传 task，或在 workflow 中直接复制 Codecov CLI upload 命令。
- 在模板预览中提交 `mise.lock`、`mise.ci.lock`、coverage report 或 Action digest。

## 外部集成验收

- 在启用了组织级 tokenless upload 的 public repository 中，验证 fork PR 与同仓库 PR 都能在不设置 `override_branch`、`override_pr` 和 `CODECOV_TOKEN` 时上传，并关联到正确的 commit 与 PR。
- 验证默认分支 OIDC 上传使用 `id-token: write`，且不依赖长期 token。
- 验证 `codecov/codecov-action@v7` 使用 mise 锁定的 Codecov CLI `11` executable 时，`fail_ci_if_error`、明确文件上传及 Codecov status/comment 保持预期行为。
- 后续升级分别审查 Codecov Action major compatibility line 与 Codecov CLI major compatibility line；template deliverable 不联动声明 minor 或 patch 版本。

这些项目记录首个真实 public repository 的采用结果，不是本仓库实现完成条件，也不要求维护专用 fixture repository。

## 完成条件

- `common`、`go-cli`、`rust` 的 capability profile 都声明 `codecov-upload = false`。
- 三个 profile 的启用和关闭分支都通过 renderer 合同验证和 validation adapter 静态检查。
- Go 和 Rust 的 coverage task 能生成约定报告；common 的占位 task 打印替换说明并以非零状态失败，直到使用者提供真实报告生成命令。
- 每个启用的 coverage adapter 恰好生成一个报告，并通过固定 `report` output 提供给 shared uploader。
- PR coverage job 在已启用 Codecov 组织级 tokenless upload 的 public repository 中无 token 上传且不拥有 OIDC，默认分支 coverage workflow 单独使用 OIDC；两者都使用 mise 锁定的 Codecov CLI `11`、`codecov/codecov-action@v7`、明确文件上传和失败阻断语义。
- PR coverage job 只响应 `pull_request`；默认分支 coverage workflow 的人工触发只执行 `main` ref。
- 默认 preview 不包含 Codecov 行为，启用 capability 的 staging 只验证对应组合，不生成额外 snapshot。
- GitHub Actions 完整 staging validation 通过；本地只运行渲染、同步检查及必要的工具单元测试。

## 参考

- [Monorepo 架构](../architecture/monorepo.md)
- [使用语义 slot 和 overlay adapter 表达模板差异](../adr/0003-use-semantic-slots-and-overlay-adapters.md)
- [使用声明式 template capability profile 和 ref-owned renderer](../adr/0006-use-declarative-template-capability-profiles-and-ref-owned-renderer.md)
- [Codecov GitHub Action 官方文档](https://github.com/codecov/codecov-action)
- [Codecov Action OIDC 配置](https://github.com/codecov/codecov-action/blob/main/_autodocs/github-action-interface.md)
