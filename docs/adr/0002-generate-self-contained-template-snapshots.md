# 生成并提交自包含的模板快照

仓库提交 `templates/<name>/` 完整快照，同时把 `shared/`、`overlays/` 和 `templates.toml` 作为可编辑来源。每份快照是对应 template profile 默认 capability 集合的完整、自包含 preview；CI 使用确定性重建检查 preview 没有过期，维护者不得直接编辑派生快照，也不为非默认 capability 组合提交额外快照。

preview 理论上可以通过 Git ref 直接获取并由使用者手动应用，但这不是应用器合同，使用者必须自行处理 metadata token。正式的 `init-project` 和 `apply-template` 按 [ADR 0006](0006-use-declarative-template-capability-profiles-and-ref-owned-renderer.md) 从 selected ref 的来源重渲染 effective capability 集合，不把快照作为输入或 fast path。

这会在仓库中保留可重建的重复内容，但换来了稳定分发、可审查 diff、离线应用和生成项目不依赖中央共享模块的性质。
