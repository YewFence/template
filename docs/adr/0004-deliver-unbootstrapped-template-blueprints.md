# 交付未引导模板并使用临时 staging 验证

template deliverable（模板交付物）刚生成时处于 unbootstrapped template（未引导模板）状态，不预解析未来项目的 mise、语言、文档锁定状态或 GitHub Action digest。完成 project instantiation（项目实例化）后，新项目通过原生工具生成并提交自己的锁定状态；monorepo 验证则在 disposable staging 中完成同样的实例化和状态生成，运行项目检查后丢弃所有生成结果。

预生成锁状态看似能让 blueprint 立即通过检查，但它会把维护者某次解析结果错误地当成未来项目状态，并要求回写多个来源。临时 staging 保留了真实生态命令和完整检查，同时让模板来源保持声明式、无生成状态。
