# Rust crates.io 发布

本指南适用于启用了 `crates-io-publish` template capability 的 Rust 项目。项目在首次发布后使用 crates.io trusted publishing(Github Action OIDC 认证)。

## 首次发布

1. 把应用模板后的改动全部提交并推送到 main。

2. Prepare Release workflow 会自动生成 release PR。它会基于当前 main 的提交记录更新：
    - Cargo.toml 中的版本；
    - Cargo.lock；
    - CHANGELOG.md。

首次发布版本建议以这个 release PR 中的 Cargo.toml 为准，不建议直接从当前 main 发布 0.1.0 ，可能会导致 Github Release 和 crate.io 版本不同步。

3. 等 release PR 的常规 CI 通过并确认内容可合并，但先不要合并。本地检出该 release 分支：

```bash
git fetch origin release
git switch --detach origin/release
```

4. 登录 [crates.io](https://crates.io/)，进入 [API Tokens](https://crates.io/settings/tokens) 页面，新建一个短期 token。权限需要允许发布新 crate，名称可以写 <crate-name>-bootstrap，过期时间尽量短。

5. 本地先做一次不上传的完整检查：

```bash
mise -E ci run crates-io:package:check
```

6. 安全地把 token 放进当前终端，不写进命令历史：

```bash
printf 'crates.io token: '
read -rs CARGO_REGISTRY_TOKEN
printf '\n'
export CARGO_REGISTRY_TOKEN
```

7. 设置环境变量，使用项目现有 mise 任务完成首次发布：

```bash
export RELEASE_TAG='v0.1.0' # release PR 中的 tag，如果是新项目，一般为 v0.1.0
export RELEASE_VERSION='0.1.0' # release PR 中的版本号，不含v
mise -E ci run crates-io:publish
```

8. 清理 Shell 环境

```bash
unset CARGO_REGISTRY_TOKEN
git switch main
```

8. 打开 crates.io 上 <crate-name> 的 Settings → Trusted Publishing → Add → GitHub，填写：

Repository owner: YourName
Repository name: YourRepo
Workflow filename: release.yml
Environment: crates-io

完成后，可选的，打开 `Require trusted publishing for all new versions` 以确保所有后续版本都必须通过 GitHub Release workflow 发布。

9. 合并 release PR 到 main。

Release workflow 会在 main 上触发，发布 GitHub Release ，crates.io 上的已有版本会自动检测到，并跳过发布。

## 后续发布

Release workflow 会先发布 GitHub Release，再把对应版本的 crate 发布到 crates.io。它根据 SemVer tag 判断是否为 prerelease，并要求 crate version 与 tag 中的版本完全一致。

如果 crates.io 发布在 GitHub Release 已经创建后失败，修复 workflow 报告的问题并重新运行同一次 Release workflow。已经发布的完全相同 crate version 会被视为完成，重跑不会再次上传。
