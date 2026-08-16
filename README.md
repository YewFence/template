# YewFence Project Templates

这个 monorepo 是 `common`、`go-cli` 和 `rust` 三个工程模板的唯一事实来源。`shared/` 与 `overlays/` 保存可编辑来源，`templates/<name>/` 保存完整、自包含的默认 template capability 集合预览；应用器始终从 selected ref 的来源重新渲染。

Template capability 在 project instantiation 前选择，改变交付行为但不成为 project identity metadata。`init-project`、`apply-template`、`export-template` 和 staging validation 共用 selected-ref 合同验证、capability resolve、隔离 render 与 metadata instantiation 的模板准备内核；其中 export 只生成独立候选树，不会触碰已有项目。

正式仓库地址固定为 `https://github.com/YewFence/template.git`，默认分支为 `main`。仓库创建前可以在本地完成维护和验证；远程应用、公开 tag 与 GitHub Release 必须等该仓库可访问后再演练。

架构、有效决策、活跃计划和历史记录统一收录在 [`docs/`](docs/README.md)。仓库开发规则和维护流程见 [`AGENTS.md`](AGENTS.md)。

## 导出候选树

只想查看某个 selected ref、template profile 与 capability 集合的完整实例化结果时，使用 `export-template`。destination 不需要是 Git 仓库，但必须不存在或为空；成功后得到的是可人工比较、选择性复制的候选树，不代表已有项目已经更新。

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  export-template \
  --ref main \
  --template rust \
  ./rust-template-main
```

非交互导出使用 profile 的 capability 默认值和完整 export metadata，因此不要求完整项目身份。CLI 参数只覆盖指定字段：

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  export-template \
  --ref main \
  --template rust \
  --enable-capability crates-io-publish \
  --cargo-package my-package \
  ./rust-template-main
```

加 `--interactive` 会从当前 profile 默认值与 CLI 覆盖值开始，依次选择未显式覆盖的 capabilities、编辑每个 metadata 字段并确认完整汇总。拒绝、`Ctrl-C`、EOF、合同错误或实例化失败都不会创建或修改 destination。export 不创建 `.git`、不应用 protected-path filtering、不生成 dependency lockfile 或 GitHub Action digest，也不运行项目检查。等价的 umbrella 命令是 `template-tool export`。

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

成功时模板变更只进入 Git index，应用器不会提交、移动分支或调用 `jj`。根级 `.gitignore`、`AGENTS*`、许可证与 notice 文件受保护并跳过；其他冲突会保留 index stages 和工作树现场供人工处理。默认情况下 `apply-template` 要求完整 metadata，并只在 selected ref 的 source checkout 之外实例化临时渲染树；传入完整 `--project-name`、`--description`、`--github-owner`、`--repo-name` 及 profile 专属选项即可在 squash apply 前替换 token。

两个入口都从 profile 默认值出发选择 template capabilities，并支持重复的 `--enable-capability <name>` 与 `--disable-capability <name>`。同方向重复项会去重；同一 capability 同时启用和关闭、名称无效或不适用于所选 template 时会在写入目标仓库前失败。成功输出中的 `Capabilities: ...` 是按名称排序的 effective enabled set，空集合显示 `Capabilities: (none)`。

`--interactive` 先询问没有被显式覆盖的适用 capabilities，再补问缺失 metadata，最后一次性确认 template、effective capabilities 和 metadata。`--keep-tokens` 只跳过 metadata 收集和项目实例化，仍会 fetch、resolve、render、选择 capability-owned outputs 并应用 staged changes；它可以与 capability overrides 和 `--interactive` 组合，但不能与 metadata 参数组合。

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

`init-project` 只接受干净、尚无 commit 且参数路径就是仓库根目录的 Git 仓库。它先从 selected ref 在临时模板树中完成合同验证、渲染及内容和路径实例化；全部准备成功后才使用普通 `git commit --allow-empty` 创建 `chore: initialize repository` 根提交，再以不套用已有项目保护列表的 clean-target policy 把完整项目写成 staged changes。它不会绕过 Git identity、签名或 hooks，也不会猜 metadata、创建 remote 或替你提交模板内容。

连接终端时可加 `--interactive`，工具会先询问未被显式覆盖的适用 capabilities，再按所选 profile 补问缺失字段、复用正式 metadata 校验，并在创建 initial commit 前请求一次汇总确认；拒绝、`Ctrl-C` 或 EOF 都不会修改目标仓库。非交互调用缺少字段会直接列出缺失项。`init-project --keep-tokens` 也只跳过 metadata 收集和实例化，不改变 capability selection、render 或完整 clean-target apply 行为。

所有 profile 都要求 `--project-name`、`--description`、`--github-owner` 和 `--repo-name`。语言 profile 还要求：

- `go-cli`：`--go-module` 与 `--binary-name`。
- `rust`：`--cargo-package` 与 `--binary-name`；crate identifier 由 Cargo package 的连字符转换为下划线。
- `common`：没有额外身份字段，但首次检查前必须替换全部 `[PLACEHOLDER]` 项目任务并加入所选语言工具。

## 查询模板能力

在应用前可以只读查询 selected ref 对某个 template 声明的全部 capabilities 及其默认状态：

```bash
uvx \
  --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" \
  list-template-capabilities \
  --ref main \
  --template rust
```

等价的 umbrella 命令是 `template-tool capabilities`，加 `--json` 可得到稳定的脚本化对象。查询命令要求显式 `--ref` 和 `--template`，不接受 target path 或 capability overrides，也不要求当前目录是 Git 仓库；它只读取指定 ref 的 capability contract，不检查或修改当前目录。

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

启用了 `crates-io-publish` capability 的 Rust 项目在首次发布前还需要配置 trusted publishing，具体步骤见 [Rust crates.io 发布指南](docs/guides/rust-crates-io-publishing.md)。这份一次性使用指南由 monorepo 维护，不会进入生成项目。

启用了 `container-image-publish` capability 的 Go CLI 项目会在 GitHub Release 成功后向 GHCR 发布同名多平台镜像；首次发布前的权限检查、本地构建方式和 tag 规则见 [Go CLI 容器镜像发布指南](docs/guides/go-cli-container-image-publishing.md)。

## Bash fallback

克隆本 monorepo 后，可以在没有 uv 时尝试：

```bash
./scripts/apply-template --ref HEAD --repo /path/to/this/monorepo --template common /path/to/repository
```

Bash launcher 会先以 selected ref 做整仓 shallow/partial fetch；系统存在 uv 时，它使用 checkout 内 `tools/template-tool/uv.lock` 的 locked 环境执行应用器。没有 uv 时才是 best-effort fallback：它要求系统已有 Git、Python 和当前应用器所需的 Python 依赖，不创建 venv、不解析 uv 锁文件，也不保证旧 launcher 与任意未来模板 ref 跨版本兼容。依赖不可用或需要严格选择版本时，使用上面的 uvx 正式路径。

## 项目状态

本地模板生成、项目实例化、staging validation、共享自动化和 Git 应用器已经实现。公开仓库验证、首个 `v0.1.0` release 和旧仓库切换仍在计划中，具体状态见 [`docs/plans/monorepo-publication.md`](docs/plans/monorepo-publication.md)。
