# Codecov 上传 capability 设计

## 状态

设计完成，待实现。本文描述 `common`、`go-cli` 和 `rust` 三个 template profile 的 `codecov-upload` template capability；实现完成后由 GitHub Actions 执行完整 staging validation，本地不要求运行完整 `mise run check`。

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

这个 task 的唯一外部合同是：在当前工作树生成至少一个 Codecov 支持的报告文件，并以确定的相对路径供上传 job 使用。Go 和 Rust 提供真实 adapter，`common` 提供可替换的占位 adapter。Codecov action、GitHub permissions、fork PR 处理和失败语义由 shared workflow 接线拥有。

这种拆分避免把 Go 的 `-coverprofile`、Rust 的 `cargo llvm-cov` 或用户未来选择的其他工具暴露成 template CLI 参数；调用者只需要知道 `mise run coverage` 和报告路径，维护者可以在 overlay 内替换实现。

### 使用 OIDC，保留 fork PR 的 tokenless 路径

第一版使用 Codecov Action 的 OIDC 认证，并在 coverage job 级别授予 `id-token: write`。不把 `CODECOV_TOKEN` 写入模板 metadata，也不要求使用者创建长期 secret 才能启用公共仓库的基础上传流程。

Codecov Action 对 fork pull request 没有父仓库 secret 时会使用其 tokenless upload 路径；workflow 必须继续使用普通 `pull_request` 触发器，不能改成 `pull_request_target`。私有仓库或组织策略需要 token 时，生成项目可以在实例化后把认证方式切换为 secret，但这不是第一版的 template interface。

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

报告文件命名是 adapter 与 uploader 之间的内部合同，不成为 project instantiation metadata。若未来 profile 需要多个报告，扩展对应 overlay fragment 的 `files` 列表即可，不增加用户 CLI 参数。

## Workflow 设计

### 触发器和 checkout

复用现有 `.github/workflows/ci.yml` 的 push、pull request 和 workflow dispatch 触发器。新增的 coverage job 使用普通 `pull_request`，checkout 当前事件对应的提交，并在运行用户代码后执行 Codecov 上传；不使用 `pull_request_target`，避免把不受信任的 PR 代码放进拥有写权限的上下文。

### 权限

coverage job 使用最小权限：

```yaml
permissions:
  contents: read
  id-token: write
```

`id-token: write` 只放在 coverage job，不提升整个 CI workflow 的默认权限。Codecov 上传不需要 `packages: write`、`contents: write` 或 pull request 写权限。

### Job 结构

shared CI layout 增加按行为命名的可选 slot，例如 `coverage_job`；profile overlay 提供完整 adapter，不在 shared layout 中写 Go、Rust 或 common 的模板名称分支。启用时 job 至少包含：

1. checkout；
2. 使用现有 `jdx/mise-action` 安装 profile 需要的 CI tools；
3. profile-specific cache（Go 使用 Go build/module cache，Rust 使用 Rust cache，common 不添加假 cache）；
4. `mise run coverage`；
5. `codecov/codecov-action` 上传明确的 report file，并启用 OIDC；
6. 失败摘要，确保缺失报告和 Codecov 错误能从 Actions 日志定位。

上传步骤应显式设置报告文件并关闭无关的自动搜索，避免工作区中其他工具生成的文件被误上传。Action 版本沿用仓库的 pinact 流程；unbootstrapped template 不包含 digest。

### mise 所有权

workflow 不复制 `go test`、`cargo llvm-cov` 或用户自定义 coverage 命令。生成报告的行为只通过 `mise run coverage` 调用，符合仓库关于“模板 workflow 只拥有触发器、权限、缓存、平台矩阵及 mise 启动基础设施”的自动化所有权规则。

## 来源和 slot 规划

| 来源 | 规划内容 |
| --- | --- |
| `templates.toml` | 三个 profile 声明 capability；CI、mise、`.gitignore` 的 conditional slot binding |
| `shared/layouts/.github/workflows/ci.yml.j2` | 增加语义 `coverage_job` slot，不理解语言名称 |
| `overlays/*/fragments/mise/` | `coverage` task 和必要的工具声明；Go/Rust 为真实 adapter，common 为占位 adapter |
| `overlays/*/fragments/workflows/ci/` | 完整 coverage job adapter，包括 cache、报告路径和上传步骤 |
| `shared/fragments/` | 只有上传步骤在三个 profile 确实稳定一致时才提升；否则保留完整 adapter，避免 shallow slot 拼接 |
| `shared/fragments/docs-ignored-paths.j2` 或 profile overlay | 忽略 `coverage.out`、`lcov.info`、`coverage.xml` 等 capability 生成的临时报告 |
| `overlays/*/mise.toml` | 按 enabled capability 检查任务、工具、workflow 和关闭时的缺席 |

是否把 Codecov badge 加入 README 不属于上传 capability 的必要输出。第一版不生成 badge，避免把 Codecov project visibility、默认 branch 和 README 文案耦合到上传合同；未来如果确有稳定需求，可以单独增加 capability-owned README fragment。

## 验证合同

三个 validation adapter 都需要展开 `codecov-upload` 的启用和关闭状态。

启用时：

- `mise` task 列表含 `coverage`；
- `.github/workflows/ci.yml` 含 coverage job；
- coverage job 调用 `mise run coverage`，不在 workflow 中复制 profile 命令；
- job 权限包含 `contents: read` 与 `id-token: write`，不要求更高写权限；
- Codecov Action 的上传路径与 profile adapter 一致；
- `fail_ci_if_error: true` 和 OIDC 认证存在；
- 对应报告路径被 `.gitignore` 忽略；
- Go/Rust 的必要工具只存在于启用分支，common 不伪造语言工具。

关闭时：

- `coverage` task、coverage job、Codecov Action 和 capability-owned ignore paths 均不存在；
- 现有主 CI check、audit、release 和 docs job 不改变行为；
- 不残留 `id-token: write` 或 Codecov 相关 secret 引用。

验证不会向 Codecov 上传真实报告，也不会依赖外部 Codecov project。Go 和 Rust adapter 可以在 disposable staging 中运行本地覆盖率生成来验证报告文件；common 只做结构合同检查，因为它的 coverage task 本来就是由使用者替换的占位实现。完整 capability 矩阵由 GitHub Actions 运行，不要求本地执行 `mise run check`。

## 使用者自定义边界

启用 capability 后，使用者需要为 `common` 替换 coverage task；Go 和 Rust 通常可以直接使用模板提供的 adapter。所有 profile 都可以在生成项目中替换覆盖率工具、报告格式、Codecov token/OIDC 配置、flags 和质量阈值，但这些修改属于项目自己的 workflow 和 mise 实现，不再由模板工具解释或实例化。

模板不为用户创建 `CODECOV_TOKEN` metadata 字段，也不把报告格式、测试包选择或阈值写入 `templates.toml`。这些内容若进入 profile 合同，会让一个通用上传能力变成按语言和项目策略不断膨胀的浅模块。

## 非目标

- 为 common 猜测或选择覆盖率生成器。
- 修改主 `test` 或 `check` task，使每次本地检查都必须生成覆盖率。
- 生成 `codecov.yml`、threshold、flags、components 或 badge。
- 使用长期 Codecov secret 作为默认认证方式。
- 上传 fork PR 的 secrets，或使用 `pull_request_target` 执行不受信任代码。
- 在模板预览中提交 `mise.lock`、`mise.ci.lock`、coverage report 或 Action digest。

## 完成条件

- `common`、`go-cli`、`rust` 的 capability profile 都声明 `codecov-upload = false`。
- 三个 profile 的启用和关闭分支都通过 renderer 合同验证和 validation adapter 静态检查。
- Go 和 Rust 的 coverage task 能生成约定报告，common 的占位 task 对使用者修改点清晰可见。
- coverage job 使用 OIDC、最小权限、明确文件上传和失败阻断语义。
- 默认 preview 不包含 Codecov 行为，启用 capability 的 staging 只验证对应组合，不生成额外 snapshot。
- GitHub Actions 完整 staging validation 通过；本地只运行渲染、同步检查及必要的工具单元测试。

## 参考

- [Monorepo 架构](../architecture/monorepo.md)
- [使用语义 slot 和 overlay adapter 表达模板差异](../adr/0003-use-semantic-slots-and-overlay-adapters.md)
- [使用声明式 template capability profile 和 ref-owned renderer](../adr/0006-use-declarative-template-capability-profiles-and-ref-owned-renderer.md)
- [Codecov GitHub Action 官方文档](https://github.com/codecov/codecov-action)
- [Codecov Action OIDC 配置](https://github.com/codecov/codecov-action/blob/main/_autodocs/github-action-interface.md)
