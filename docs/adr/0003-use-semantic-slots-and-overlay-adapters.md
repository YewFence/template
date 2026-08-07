# 使用语义 slot 和 overlay adapter 表达模板差异

共享 layout 只暴露按行为语义命名的 slot，Go、Rust 和 common 的真实差异由 shared 或 overlay fragment 提供。大型构建矩阵、语言缓存和语言专属任务可以作为完整 adapter 保留，不为了文本一致而拆成细碎插入点。

这条边界避免 layout 退化为任意文本拼接接口，也避免共享层通过模板名称和条件分支理解每种语言。只有多个模板确实共享稳定行为时，代码才提升到 shared 来源。
