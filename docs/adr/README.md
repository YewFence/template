# 架构决策

本目录只记录难以撤销、存在真实取舍，而且无法仅从代码理解原因的长期决策。当前系统说明见 [`docs/architecture/monorepo.md`](../architecture/monorepo.md)，实施过程和已撤销方案见 [`docs/archive/2026-08-monorepo-convergence/`](../archive/2026-08-monorepo-convergence/)。

1. [使用 monorepo 作为模板的唯一事实来源](0001-use-monorepo-as-the-source-of-truth.md)
2. [生成并提交自包含的模板快照](0002-generate-self-contained-template-snapshots.md)
3. [使用语义 slot 和 overlay adapter 表达模板差异](0003-use-semantic-slots-and-overlay-adapters.md)
4. [交付未引导模板并使用临时 staging 验证](0004-deliver-unbootstrapped-template-blueprints.md)
5. [分离项目初始化与已有仓库模板应用](0005-separate-project-initialization-from-template-application.md)
