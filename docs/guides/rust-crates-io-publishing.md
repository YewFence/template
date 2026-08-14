# Rust crates.io 发布

本指南适用于启用了 `crates-io-publish` template capability 的 Rust 项目。项目在首次发布后使用 crates.io trusted publishing。

## 首次发布

1. 使用临时或细粒度 crates.io API token 手动运行一次 `cargo publish`，在 crates.io 上创建 crate。
2. 在 crates.io 配置 trusted publisher，GitHub owner 和 repository 使用项目的实际值，workflow file 填写 `release.yml`，environment 填写 `crates-io`。
3. 在 GitHub 仓库中创建 `crates-io` environment，并根据项目需要配置 protection rules。

首次发布完成后，不要在 GitHub 中保存长期有效的 crates.io token secret。

## 后续发布

Release workflow 会先发布 GitHub Release，再把对应版本的 crate 发布到 crates.io。它根据 SemVer tag 判断是否为 prerelease，并要求 crate version 与 tag 中的版本完全一致。

如果 crates.io 发布在 GitHub Release 已经创建后失败，修复 workflow 报告的问题并重新运行同一次 Release workflow。已经发布的完全相同 crate version 会被视为完成，重跑不会再次上传。
