# Go CLI 容器镜像发布

`go-cli` profile 的 `container-image-publish` template capability 默认关闭。启用后，生成项目通过 `ko` 从 `./cmd/<binary-name>` 构建镜像，不需要 Dockerfile 或 `ko.yaml`。

## 首次配置

首次发布前，确认仓库允许 GitHub Actions 使用 `GITHUB_TOKEN` 写入 packages。workflow 只为镜像发布 job 授予 `contents: read` 与 `packages: write`，不会读取长期 registry secret。

首次镜像发布后，按项目需要检查 GHCR package 的 visibility，并确认 package 已与来源 repository 关联。组织策略限制 package 创建或可见性时，需要由组织管理员放行相应权限。

## 本地构建

项目引导并安装 `mise.ci.toml` 中的工具后，使用 CI environment 运行本地构建任务：

```bash
MISE_ENV=ci mise run container:build
```

该任务使用 `ko build --local` 将单平台镜像写入本机 Docker-compatible daemon，不登录或推送 registry。默认使用 `ko.local` repository 和当前平台；需要指定平台时设置 `CONTAINER_IMAGE_PLATFORM`：

```bash
MISE_ENV=ci CONTAINER_IMAGE_PLATFORM=linux/arm64 mise run container:build
```

## 发布行为

正式 release workflow 先发布 GitHub Release，再使用同一次 release 解析出的 tag、checkout ref 和 prerelease 状态调用 `mise run container:publish`。默认 repository 是实例化后的小写 `ghcr.io/<owner>/<repository>`，publish task 使用 `--platform=all` 生成多平台 manifest。

版本 `v1.2.3` 会发布 `:v1.2.3`；稳定版本同时更新 `:latest`，预发布版本只发布自身 tag。workflow dispatch 可以对同一个 release tag 重试镜像发布，不需要重新创建 tag。

生成项目可以通过 `CONTAINER_IMAGE_REPOSITORY` 覆盖完整 registry/repository，但模板不会为 Docker Hub、私有 registry 或自定义 Dockerfile 提供认证与兼容性合同。
