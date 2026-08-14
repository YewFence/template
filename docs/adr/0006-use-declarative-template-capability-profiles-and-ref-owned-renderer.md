# 使用声明式 template capability profile 和 ref-owned renderer

`templates.toml` schema v2 由每个 template profile 以布尔表声明适用 capabilities 及其默认状态。Template capability 在 project instantiation 之前选择，属于 template profile 合同，不是 project identity metadata，不产生 identity token 或 provenance 状态。`render`、`sync:check`、`init-project`、`apply-template`、`export-template` 和 staging validation 共享同一个 capability resolver；未知 schema、未知 capability 和互相冲突的 override 必须明确失败。

`templates/<name>/` 只保存默认 capability 集合的完整、自包含 template deliverable preview，不是应用入口的输入或 fast path。输入 branch、tag 或 commit 在一次应用会话中只解析为一个 commit；该 selected ref 同时拥有 source、schema、renderer 和 application engine。工具对该 commit 做整仓 shallow/partial fetch，在只读 source checkout 中使用其锁定的工具环境，并把 effective capability 集合重渲染到调用者提供的隔离 destination。

`init-project`、`apply-template`、`export-template` 和 staging validation 共享同一个模板准备内核：完整验证 selected-ref profile 合同、解析 capabilities、渲染隔离项目树，并按入口需要执行 project instantiation。准备完成后，`init-project` 才创建 initial commit，`apply-template` 才进入 protected-path filtering 与 squash apply，`export-template` 才将完整候选树原子发布到独立 destination，staging validation 则引导并检查 disposable project 后丢弃全部生成状态。export 不检查或修改已有项目，也不提供模板升级合同。具体 schema、CLI、slot 和 validation matrix 记录在 [Monorepo 架构](../architecture/monorepo.md) 中。

这项决策不取代 ADR 0002、0003 或 0005。它放弃 snapshot fast path、sparse checkout 和“本地新 engine 解释旧 ref”的兼容承诺，换取原子、可审查的模板发行边界，并保证准备失败时目标仓库保持不变。
