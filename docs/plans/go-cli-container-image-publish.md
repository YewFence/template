# go-cli 容器镜像发布 capability 设计

## 状态

本地实现完成，待 GitHub Actions 执行完整 staging validation。本文描述 `go-cli` 模板的 `container-image-publish` template capability；本地不要求运行完整 `mise run check`。

## 背景

`go-cli` 当前 release workflow 会构建多个平台的二进制并发布 GitHub Release，但不会发布容器镜像。Go CLI 已经拥有明确的可执行入口 `./cmd/{{BINARY_NAME}}`，可以使用 `ko` 直接从 Go 包构建镜像，不需要维护 Dockerfile、Docker build context 或独立的容器构建矩阵。

第一版只解决一个稳定的 happy path：在正式 release 成功后，用 `ko` 构建多平台镜像并发布到 `ghcr.io`。其他 registry、Dockerfile 工作流、非 Go 项目和运行时基础镜像定制不属于这一版的模板合同。

## 设计决策

### 独立 capability

在 `[templates.go-cli.capabilities]` 中声明：

```toml
container-image-publish = false
```

该 capability 与 `codecov-upload`、`crates-io-publish` 等能力独立启用，不把镜像发布和覆盖率上传绑定成一个组合。它属于 `go-cli` profile；`common` 没有稳定的应用入口，`rust` 也暂时没有确定的容器运行时语义，因此第一版不向它们声明该 capability。

### 固定 GHCR，不建立 registry provider 接口

发布目标固定为 `ghcr.io/<owner>/<repository>`，其中 owner 和 repository 来自实例化后的 GitHub identity。第一版不增加 registry、用户名、镜像路径、认证方式或 Dockerfile provider 参数。当前只有一个真实 adapter，抽象出 provider seam 只会把第三方工具的内部参数暴露给模板使用者。

生成项目仍然可以在实例化后修改 `mise` task 或 workflow，改用 Docker Hub、私有 registry 或自定义 Dockerfile；模板不承诺这些修改的兼容性。

### 使用 `ko`，不生成 Dockerfile

`ko` 是 `go-cli` 的容器构建 adapter。它直接从 `./cmd/{{BINARY_NAME}}` 构建 Go 应用镜像，并负责镜像层、基础镜像和多平台 manifest 的生成。生成项目的 `mise.ci.toml` 使用 `aqua:ko-build/ko` 声明兼容版本线，锁定状态由 bootstrapped project 使用原生 mise 命令生成，不在 template deliverable 中预生成。

这个选择保留 Go CLI 的真实差异在 overlay 中，同时让 release workflow 只负责权限、登录、触发和发布基础设施，项目行为继续由稳定的 mise task 拥有。

## Capability 接口

启用 capability 后，生成项目必须拥有以下接口：

| 接口 | 责任 |
| --- | --- |
| `mise run container:build` | 在本地构建单平台镜像，不登录或推送任何 registry |
| `mise run container:publish` | 在 release 环境中构建多平台镜像并推送到 GHCR |
| `CONTAINER_IMAGE_REPOSITORY` | publish 时可选覆盖目标 repository；workflow 默认设置为实例化后的 GHCR 路径，build 时默认使用 `ko.local` |
| `CONTAINER_IMAGE_PLATFORM` | build 时可选指定单个平台；publish 不使用该覆盖值，而是使用 capability 固定的多平台集合 |
| `RELEASE_TAG` | publish 时的镜像 release tag，默认来自现有 release workflow |
| `RELEASE_PRERELEASE` | publish 时是否为预发布版本；由 release job 输出提供 |
| `./cmd/{{BINARY_NAME}}` | `ko` 的 Go main package 输入，属于 go-cli 固定结构 |

`container:build` 是本地可测试的 no-push 接口，不要求 GitHub、GHCR 或 registry credentials，但需要本机有可用的 Docker-compatible daemon 供 `ko --local` 写入镜像；`container:publish` 只由 release workflow 调用。调用者不需要了解 `ko` 的 base image、层布局、manifest 细节或认证实现。除上述环境变量外，不为第一版暴露 `ko` 的全部命令行参数。

### 镜像名称和 tag

默认 repository 为 `ghcr.io/${GITHUB_OWNER}/${REPO_NAME}`，发布前规范化为小写，以满足 OCI registry reference 的约束。允许通过 `CONTAINER_IMAGE_REPOSITORY` 覆盖 repository，覆盖值必须仍然是完整的 registry/repository 名称；workflow 不为覆盖值自动拼接 owner 或 repository。

镜像 tag 与现有 release tag 保持一致：`v1.2.3` 发布为 `:v1.2.3`。稳定版本额外发布 `:latest`；预发布版本只发布自身的版本 tag，不移动 `latest`。第一版不发布无 `v` 前缀的第二套 tag，也不从 Git SHA 生成额外 tag。

本地 `container:build` 不使用 release tag，也不更新 `latest`。它将镜像写入 `ko.local` 本地命名空间，输出可供本机 Docker 工具检查的镜像引用；本地 tag 只用于开发验证，不属于发布合同。

### 多平台和构建行为

`container:build` 使用 `ko build --local` 从 `./cmd/{{BINARY_NAME}}` 构建单个平台镜像，默认使用当前 `ko` compatibility line 的本地平台；可以通过 `CONTAINER_IMAGE_PLATFORM` 选择一个明确的平台。它不创建多平台 manifest、不调用 GHCR，也不需要 `--bare` 的发布路径语义。

`container:publish` 使用 `ko build` 构建多平台镜像，默认使用 `--platform=all`，至少覆盖 `linux/amd64` 与 `linux/arm64`，并使用 `--bare` 使最终路径保持为指定 repository，不附加 Go import path 或 hash 后缀。具体平台集合由当前 `ko` compatibility line 决定，不暴露为 template CLI 参数。只有 publish task 拥有 push 行为，workflow 只提供认证后的环境。

镜像构建使用 `ko` 默认的 Go 运行时基础镜像策略。第一版不生成 `Dockerfile`、`ko.yaml` 或自定义 base image 配置；需要自定义运行时镜像时，由实例化后的项目自行添加并修改 task。

## 来源和 slot 规划

实现应按现有 shared layout 与 overlay adapter 模型组织：

| 来源 | 规划内容 |
| --- | --- |
| `templates.toml` | 声明 capability、release workflow 的 conditional slot binding |
| `overlays/go-cli/fragments/mise/ci/` | 声明 `ko` 工具、`container:build` task 和 `container:publish` task |
| `shared/layouts/.github/workflows/release.yml.j2` | 增加语义 slot，例如 `publish_container_job`，不包含 Go 分支判断 |
| `overlays/go-cli/fragments/workflows/release/` | 提供完整的 Go 镜像发布 job adapter |
| `overlays/go-cli/mise.toml` | 验证 capability 的任务、工具和 workflow 输出 |
| `overlays/go-cli/fragments/renovate/profile.json` | 如需 capability-specific Renovate 行为，只增加该 capability 的贡献；普通 mise/action 更新继续由已有配置负责 |

发布 job 应在现有 `release` job 成功后执行，依赖 `[version, release]`，并且只调用 `mise run container:publish`。这样 GitHub Release 仍然是现有发布主流程，镜像发布失败时可以通过同一个 tag 的 workflow dispatch 重试，而不需要重新创建版本 tag。镜像 job 不依赖二进制 artifact，因为 `ko` 直接从源代码构建镜像；它也不应复用跨平台 release artifact，以免把容器构建错误地绑定到压缩包格式。

### 权限和认证

镜像 job 使用最小权限：

```yaml
permissions:
  contents: read
  packages: write
```

认证使用 GitHub Actions 的 `GITHUB_TOKEN` 登录 GHCR，且只允许在模板现有 release 触发条件满足后执行。job 不读取长期 registry secret，不使用 `pull_request_target`，不为来自 fork 的未信任代码授予写入 packages 的权限。workflow dispatch 仍然沿用现有的 release tag 校验和 checkout ref 逻辑。

实现可以使用官方 `ko` 登录方式或等价的 GHCR 登录 action，但认证必须在 task 执行前完成，并让 `ko` 使用标准 Docker credential store。具体 action 版本由 bootstrapped project 的 Action pin 流程生成；模板预览不携带 digest。

## 验证合同

`go-cli` validation adapter 需要根据 enabled capability set 展开并检查 `container-image-publish` 的两种状态：

启用时：

- `mise.ci.toml` 含 `ko` 工具；
- `mise` task 列表同时含 `container:build` 和 `container:publish`；
- task 的入口是 `./cmd/{{BINARY_NAME}}`，不是硬编码的模板名称；
- `container:build` 使用 local/no-push 模式，能够在 disposable staging 中构建单平台镜像而不读取 registry credentials；
- release workflow 含镜像发布 job，并包含 `packages: write`；
- job 调用 `mise run container:publish`，而不是在 workflow 中复制 `ko` 命令；
- job 的依赖和 release tag 条件与现有 release workflow 一致；
- 目标默认指向 GHCR，稳定版本和预发布版本的 tag 分支存在；
- 不生成 Dockerfile、`ko.yaml` 或新的预生成 lockfile。

关闭时：

- `ko` 工具以及 `container:build`、`container:publish` task 都不存在；
- release workflow 不含镜像发布 job、GHCR 登录步骤或 `packages: write`；
- `go-cli` 的其他 release job 与 artifact 行为不变。

staging validation 不向真实 GHCR 推送镜像。它在 disposable project 中使用 `mise run container:build` 验证渲染、实例化、Go main package 和本地镜像构建，再静态验证 `container:publish` 的 workflow、权限、tag 和多平台合同；整个过程不读取真实 registry credentials。完整矩阵由 GitHub Actions 运行，不要求维护者在本地运行 `mise run check`。

## 文档和使用者体验

模板使用文档应说明：启用 `container-image-publish` 后，项目的 release tag 会产生 GHCR 镜像，稳定版本还会更新 `latest`；首次发布前需要确认仓库允许 GitHub Actions 写入 packages，并在需要时将 package visibility 与 repository 关联。

第一版不生成专门的 Docker 使用指南、不修改项目 identity metadata，也不把 registry 自定义写成 template CLI 参数。生成项目 README 可以通过 capability-owned fragment 增加一句发布说明，但不能复制完整 workflow 或 `ko` 参数列表。

## 非目标

- 支持 Docker Hub、Quay、Amazon ECR 或任意私有 registry。
- 为镜像发布增加独立 release versioning 或重复发布协议。
- 通过 Dockerfile、Buildx 或 Compose 取代 `ko`。
- 发布 nightly、branch、commit SHA 或无 `v` 前缀的额外 tag。
- 在 `common` 或 `rust` 中提前声明未定义的容器运行时行为。
- 在 monorepo 中生成 `mise.ci.lock`、Go checksum 或 GitHub Action digest。

## 完成条件

- `templates.go-cli.capabilities` 声明 `container-image-publish = false`。
- 默认 preview 不包含镜像发布行为；启用 capability 的 staging case 能渲染完整 workflow 和 mise task。
- 启用分支同时提供可本地执行的 `container:build` 和只供 release workflow 调用的 `container:publish`。
- capability 开启和关闭都通过对应 validation adapter 的静态合同检查。
- release job 使用最小 GHCR 权限，并能从现有 release metadata 得到 repository、tag 和 prerelease 状态。
- GitHub Actions 完整 staging validation 通过；本地只运行渲染、同步检查及必要的工具单元测试。

## 参考

- [Monorepo 架构](../architecture/monorepo.md)
- [使用语义 slot 和 overlay adapter 表达模板差异](../adr/0003-use-semantic-slots-and-overlay-adapters.md)
- [使用声明式 template capability profile 和 ref-owned renderer](../adr/0006-use-declarative-template-capability-profiles-and-ref-owned-renderer.md)
- [ko 官方文档](https://ko.build/)
- [ko `build` 参考](https://ko.build/reference/ko_build)
