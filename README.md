# YewFence Project Templates

这个 monorepo 是 `common`、`go-cli` 和 `rust` 三个工程模板的唯一事实来源。`shared/` 与 `overlays/` 保存可编辑来源，`templates/<name>/` 保存完整、自包含、可直接应用的生成快照。

正式仓库地址固定为 `https://github.com/YewFence/template.git`，默认分支为 `main`。仓库创建前可以在本地完成维护和验证；远程应用、公开 tag 与 GitHub Release 必须等该仓库可访问后再演练。

## Monorepo 维护者

不要直接编辑 `templates/<name>/`。共享行为改在 `shared/`，模板专属行为改在 `overlays/<name>/`，然后重新渲染快照。

```bash
mise install
mise run render
mise run sync:check
mise run check
```

常用维护入口：

| 命令 | 用途 |
| --- | --- |
| `mise run render [template]` | 从真实来源重新生成一个或全部模板快照 |
| `mise run sync:check [template]` | 只读检查来源与快照是否同步 |
| `mise run check [template]` | 在隔离父级和全局 mise 配置后运行模板完整检查 |
| `MISE_OFFLINE=0 mise run locks:update [--bump] <template>` | 用 mise、Go、Cargo、pnpm 等原生命令事务式更新声明的依赖状态 |
| `MISE_OFFLINE=0 mise run actions:update` | 用 pinact 更新真实 workflow 来源，再事务式重渲染快照 |
| `uv run --project tools/template-tool python -m unittest discover -s tools/template-tool/tests -v` | 运行 renderer、更新器和本地 Git 应用器测试 |

`locks:update` 和 `actions:update` 是主动写操作。它们只允许修改声明的真实来源，验证失败会恢复来源与模板快照；锁文件不得手工编辑。

## 应用到已有仓库

正式支持路径是 uv。目标必须是已有至少一个 commit 的干净 Git 仓库，且不能处于 merge、rebase、cherry-pick 或 revert 中。

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  apply-template \
  --template go-cli \
  /path/to/repository
```

可选模板是 `common`、`go-cli` 和 `rust`。需要可复现输入时，把 `@main` 与 `--ref` 一起换成相同的 tag 或完整 commit：

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@v0.1.0#subdirectory=tools/template-tool" \
  apply-template \
  --repo https://github.com/YewFence/template.git \
  --ref v0.1.0 \
  --template rust \
  /path/to/repository
```

成功时模板变更只进入 Git index，应用器不会提交、移动分支或调用 `jj`。根级 `.gitignore`、`AGENTS*`、许可证与 notice 文件受保护并跳过；其他冲突会保留 index stages 和工作树现场供人工处理。

```bash
git status
git diff
git diff --cached
git diff --check
```

解决冲突后运行 `git add`，审查无误再自行提交。要取消整次应用，运行 `git reset --hard HEAD`；这条命令只适用于应用前已确认干净的目标仓库。

detached HEAD 和 colocated Jujutsu 仓库受支持，但必须先完成、解决或取消这次 Git 应用，再继续普通 `jj` 操作。`v0.1.0` 不提供重复 apply 或模板升级合同。

## 新项目流程

`apply-template` 不会隐式创建仓库或首个提交。新项目使用独立的 `init-project` 入口建立 Git 基线并应用选定模板：

```bash
mkdir my-project
cd my-project
git init -b main

uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  init-project \
  --template common \
  .
```

`init-project` 只接受干净、尚无 commit 且参数路径就是仓库根目录的 Git 仓库。它先使用普通 `git commit --allow-empty` 创建 `chore: initialize repository` 根提交，再复用 `apply-template` 的 sparse fetch、保护路径和 squash apply；模板内容仍只进入 staged changes，等待你审查和提交。它不会绕过 Git identity、签名或 hooks，也不会猜项目名、创建 remote 或替你提交模板内容。

应用后按模板类型完成初始化：

- `go-cli`：审查 staged changes 后运行 `mise trust`、`mise install` 和 `mise run init`，填写 module、命令名、owner、repo 与描述；初始化工具会更新模板占位符。
- `rust`：将 `README.template.md`、`AGENTS.template.md` 作为项目文件，替换 `{{PROJECT_NAME}}` 等 metadata token，更新 crate、binary 与示例源码，再安装工具和 hooks。
- `common`：将模板文档作为项目文件，替换 metadata token 和全部 `[PLACEHOLDER]` mise 任务，加入语言工具、Renovate manager 与原生锁文件，再安装工具和 hooks。

所有模板初始化完成后都应执行：

```bash
mise trust
mise install
mise run hooks:install
mise run check
```

## Bash fallback

克隆本 monorepo 后，可以在没有 uv 时尝试：

```bash
./scripts/apply-template --template common /path/to/repository
```

Bash launcher 只是 best-effort fallback：它要求系统已有 Git、Python 和当前应用器所需的 Python 依赖，不创建 venv、不解析 uv 锁文件，也不保证旧 launcher 与任意未来模板 ref 跨版本兼容。依赖不可用或需要严格选择版本时，使用上面的 uvx 正式路径。

## 当前发布边界

本地 renderer、事务式锁/action 更新器、三个模板检查、共享 workflow、根 CI 和 Git 应用器测试已经实现。正式 `apply-template` 与 `init-project` 还从当前 monorepo HEAD sparse fetch 三份真实快照并分别应用到临时仓库，验证 staged 结果、保护路径、commit provenance、零冲突、无 `MERGE_HEAD`、HEAD 不移动以及新项目根提交。三份模板也在离线临时 Git 仓库中真实演练了 `release:version`、tag、notes、changelog、幂等 tag 创建和 package adapter：common 不生成附件，Go/Rust 各生成一个 Linux x86_64 archive。

以下外部步骤不属于当前本地收敛结果，需未来获得明确授权后另行执行：

1. 添加官方 remote 并验证公开 sparse fetch 与 uvx 安装。
2. 端到端演练不可移动的首个 `v0.1.0` tag、GitHub Release、release PR 与三模板资产行为。
3. 公开验证通过后再执行旧仓库归档和唯一维护入口切换。

根配置与三个模板配置已通过官方 `renovate/renovate:44.13.2` 容器中的 `renovate-config-validator --strict --no-global`。
