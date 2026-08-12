# 使用语义 slot 和 overlay adapter 表达模板差异

共享 layout 只暴露按行为语义命名的 slot，Go、Rust 和 common 的真实差异由 shared 或 overlay fragment 提供。大型构建矩阵、语言缓存和语言专属任务可以作为完整 adapter 保留，不为了文本一致而拆成细碎插入点。

Template profile 可以按 [ADR 0006](0006-use-declarative-template-capability-profiles-and-ref-owned-renderer.md) 声明 capability-owned output、conditional slot binding 和 variant slot binding。完整 profile 合同必须独立于当前 enabled capability 集合验证，关闭 capability 不能掩盖无效 output selector、fragment 或 slot 分支。Capability 归属只存在于声明式合同中，不通过 Jinja 条件或 source 目录命名表达。

这条边界避免 layout 退化为任意文本拼接接口，也避免共享层通过模板名称和条件分支理解每种语言。只有多个模板确实共享稳定行为时，代码才提升到 shared 来源。
