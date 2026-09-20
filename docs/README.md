# Documentation

Current guides, architecture, decisions, and plans for this monorepo.

## For Template Users

- [Agent skill](../skills/use-template/SKILL.md): the same flow driven by a coding agent — profile and capability selection, instantiation, conflict resolution, and bootstrap to a passing check.
- [Usage guide](guides/use-template.md): every way to consume the templates — init, apply, export, capability queries, non-interactive usage, and the Bash fallback.
- [CLI reference](reference/cli.md): every command and option, generated from the tool's `--help` output.
- [Uploading coverage to Codecov](guides/codecov-upload.md): public-repository prerequisites, PR tokenless uploads, default-branch OIDC, and profile-specific coverage reports.
- [Publishing container images (Go CLI)](guides/go-cli-container-image-publishing.md): local builds, GHCR permissions, and release behavior with the `container-image-publish` capability.
- [Publishing to crates.io (Rust)](guides/rust-crates-io-publishing.md): first-release setup and the ongoing release flow with the `crates-io-publish` capability.

## For Maintainers

- [Monorepo 架构](architecture/monorepo.md)：当前来源模型、生成流程、验证边界和应用器职责。
- [架构决策](adr/)：解释难以从代码直接看出的长期取舍。
- [活跃计划](plans/)：尚未完成的工作，只保留未来步骤。
- [Agent skills](agents/)：仓库共享工作流与领域命名约定。

历史文档（`archive/` 与已完成的发布计划）已在公开发布前移除，可通过 Git 历史追溯；已撤销的方案不构成有效合同。
