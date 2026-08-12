# 分离项目初始化与已有仓库模板应用

`init-project` 只服务干净的新仓库，可以在隔离 destination 中完整实例化 metadata 并应用所有模板文件。交互模式只补问缺失字段，并在创建 initial commit 前确认；取消不改变目标 repository。`apply-template` 只服务已有历史的干净仓库，默认在隔离 destination 中显式实例化传入 metadata；`--keep-tokens` 才保留未实例化 blueprint 行为。它不扫描、推断或替换目标 repository 原有文件中的 token，并跳过受保护的根级身份与工作区控制文件。

两个入口按 [ADR 0006](0006-use-declarative-template-capability-profiles-and-ref-owned-renderer.md) 从 selected ref 的 source、schema 和 renderer 共享 capability-aware 模板准备内核。完整合同验证、capability resolve、render、metadata instantiation、protected path filtering 和临时模板 commit 构造完成后，工具才重新验证并触碰目标仓库；`init-project` 先准备模板 commit，再创建 initial commit。准备成功后两个入口共享 Git squash apply 内核，但不根据目标状态隐式切换模式。

显式入口让高风险的身份物化只发生在新项目生命周期，已有项目则始终保留人工审查边界；先准备后触碰目标也避免 schema、render 或实例化失败留下半初始化仓库。
