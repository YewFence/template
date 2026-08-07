# YewFence Project Templates

这个 monorepo 是 `common`、`go-cli` 和 `rust` 三个工程模板的唯一事实来源。`shared/` 与 `overlays/` 保存可编辑来源，`templates/<name>/` 保存完整、自包含、可直接应用的生成快照。

正式仓库地址固定为 `https://github.com/YewFence/template.git`，默认分支为 `main`。仓库创建前可以在本地完成维护和验证；远程应用、公开 tag 与 GitHub Release 必须等该仓库可访问后再演练。

架构、有效决策、活跃计划和历史记录统一收录在 [`docs/`](docs/README.md)。仓库开发规则和维护流程见 [`AGENTS.md`](AGENTS.md)。

## 应用到已有仓库

正式支持路径是 uv。目标必须是已有至少一个 commit 的干净 Git 仓库，且不能处于 merge、rebase、cherry-pick 或 revert 中。

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  apply-template \
  --ref main \
  --template go-cli \
  --interactive \
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
  --keep-tokens \
  /path/to/repository
```

成功时模板变更只进入 Git index，应用器不会提交、移动分支或调用 `jj`。根级 `.gitignore`、`AGENTS*`、许可证与 notice 文件受保护并跳过；其他冲突会保留 index stages 和工作树现场供人工处理。默认情况下 `apply-template` 要求完整 metadata，并只实例化 fetched template tree；传入完整 `--project-name`、`--description`、`--github-owner`、`--repo-name` 及 profile 专属选项即可在 squash apply 前替换 token。`--interactive` 只补问缺失字段，`--keep-tokens` 显式保留未实例化 blueprint 行为，且不能与 metadata 或交互模式混用。

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
  --ref main \
  --template common \
  --project-name "My Project" \
  --description "Describe the project" \
  --github-owner YewFence \
  --repo-name my-project \
  .
```

`init-project` 只接受干净、尚无 commit 且参数路径就是仓库根目录的 Git 仓库。它先使用普通 `git commit --allow-empty` 创建 `chore: initialize repository` 根提交，在临时模板树中完成内容和路径实例化，再以不套用已有项目保护列表的 clean-target policy 把完整项目写成 staged changes。它不会绕过 Git identity、签名或 hooks，也不会猜 metadata、创建 remote 或替你提交模板内容。

连接终端时可加 `--interactive`，工具会按所选 profile 补问缺失字段、复用正式 metadata 校验，并在创建 initial commit 前请求汇总确认；拒绝、`Ctrl-C` 或 EOF 都不会修改目标仓库。非交互调用缺少字段会直接列出缺失项。

所有 profile 都要求 `--project-name`、`--description`、`--github-owner` 和 `--repo-name`。语言 profile 还要求：

- `go-cli`：`--go-module` 与 `--binary-name`。
- `rust`：`--cargo-package` 与 `--binary-name`；crate identifier 由 Cargo package 的连字符转换为下划线。
- `common`：没有额外身份字段，但首次检查前必须替换全部 `[PLACEHOLDER]` 项目任务并加入所选语言工具。

实例化完成后，按以下真实命令生成并提交项目自己的依赖锁定状态与 Action digest：

```bash
mise trust
mise -E ci lock
mise install --locked
mise run deps:update
mise run docs:install
mise run actions:update
mise run hooks:install
mise run check
```

把生成的 `mise.lock`、`mise.ci.lock`、Go/Cargo 依赖状态、`docs/pnpm-lock.yaml` 以及 pinact 对 workflow 的修改与项目源码一起审查并提交。`docs:install` 用于首次解析和安装；日常 `docs:build`、`docs:dev` 与 `docs:preview` 只消费已提交锁文件。

## Bash fallback

克隆本 monorepo 后，可以在没有 uv 时尝试：

```bash
./scripts/apply-template --ref HEAD --repo /path/to/this/monorepo --template common /path/to/repository
```

Bash launcher 只是 best-effort fallback：它要求系统已有 Git、Python 和当前应用器所需的 Python 依赖，不创建 venv、不解析 uv 锁文件，也不保证旧 launcher 与任意未来模板 ref 跨版本兼容。依赖不可用或需要严格选择版本时，使用上面的 uvx 正式路径。

## 项目状态

本地模板生成、项目实例化、staging validation、共享自动化和 Git 应用器已经实现。公开仓库验证、首个 `v0.1.0` release 和旧仓库切换仍在计划中，具体状态见 [`docs/plans/monorepo-publication.md`](docs/plans/monorepo-publication.md)。
