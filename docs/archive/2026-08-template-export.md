# Template export 实施记录

## 状态

已实现独立的 `export-template` 入口及 `template-tool export` umbrella 命令。它从 selected ref 的锁定工具环境执行，复用模板准备与 project instantiation 内核，并将完整候选树原子发布到不存在或为空的 destination。

本计划增加独立的 `export-template` 入口。它复用 selected ref 拥有的模板准备与 project instantiation 引擎，把指定 template profile 和 capability 集合生成为独立候选树，但不进入 `init-project` 或 `apply-template` 的 Git 生命周期。

## 问题

当前使用者必须完整执行 `init-project`，或者把模板直接应用到已有仓库，才能查看某个 selected ref 和 capability 集合对应的实例化结果。前者要求 unborn Git 仓库、完整项目身份和 initial commit，后者会修改目标仓库的 index 与工作树；两者都不适合只想检查新版文件并人工选择更新内容的场景。

Template export 只提供人工更新的输入材料。它不判断哪些文件应被复制，不合并现有修改，不推断项目身份，也不承诺重复 apply、provenance 或模板升级协议。

## 生命周期边界

`export-template` 是模板准备内核上的独立 adapter，不是 `init-project` 的快速模式，也不是 `apply-template` 的 dry run。

```text
selected ref
    -> profile contract validation
    -> capability resolution
    -> isolated render
    -> metadata instantiation
    -> standalone candidate tree
```

该入口复用 selected ref 的 source、schema、renderer、capability resolver 和 project instantiation 引擎。它不创建 Git 仓库、initial commit、临时模板 commit、index 或 squash apply，也不执行 protected-path filtering。

## CLI 接口

正式命令为 `export-template`，umbrella 命令为 `template-tool export`。

```bash
export-template \
  --ref main \
  --template rust \
  --interactive \
  ./rust-template-main
```

第一版支持以下输入：

- destination path；
- `--repo`、`--ref` 和 `--template`；
- `--interactive`；
- 可重复的 `--enable-capability` 与 `--disable-capability`；
- 与 `init-project` 相同的静态 metadata 参数。

`--ref` 和 `--template` 必须显式提供。命令不根据当前目录、destination 或已有项目内容猜测 template、ref、capabilities 或 metadata。

## 交互流程

交互模式依次完成 capability selection、metadata editing 和一次汇总确认。

Capability 问题从 selected-ref profile 默认值开始。通过 CLI 显式启用或关闭的 capability 不再询问；未被显式覆盖的 capability 使用 profile 当前值作为交互默认值。

每个必填 metadata 字段都显示当前默认值。直接按 Enter 接受该值，输入内容则替换本次值，因此使用者可以一路按 Enter 生成纯占位版本，也可以只把少数字段改成现有项目的真实身份。

```text
Enable capability crates-io-publish? (y/N)
Enable capability docs-site? (Y/n)

Project Name (REPLACE ME: project name):
Description (REPLACE ME: project description):
GitHub Owner (replace-me-owner):
Repository Name (replace-me-repository):
Cargo Package (replace-me-package):
Binary Name (replace-me-binary):
```

CLI metadata 参数为交互提供初始值，而不是跳过对应问题。这样脚本可以在非交互模式中使用参数，人工调用也仍有机会在最终导出前修改它们。

最终确认显示 repository、ref、resolved commit、template、effective capabilities、metadata 和 destination。拒绝、`Ctrl-C` 或 EOF 不创建或修改 destination。

## 非交互模式

不带 `--interactive` 时，命令使用 profile capability defaults、template export metadata 和 CLI 参数直接生成候选树，不要求调用者提供完整 metadata。

```bash
export-template \
  --ref main \
  --template rust \
  ./rust-template-main
```

非交互模式适合快速生成纯占位版本。使用者也可以只覆盖少数字段，其余字段继续使用 template 声明的 export metadata：

```bash
export-template \
  --ref main \
  --template rust \
  --enable-capability crates-io-publish \
  --cargo-package my-package \
  ./candidate
```

## Export metadata

每个 template profile 在 `templates.toml` 中声明完整的 export metadata。它必须覆盖该 profile 的全部 required metadata，并通过正式 metadata 与路径安全校验。

```toml
[templates.rust.instantiation.export.metadata]
project_name = "REPLACE ME: project name"
description = "REPLACE ME: project description"
github_owner = "replace-me-owner"
repo_name = "replace-me-repository"
cargo_package = "replace-me-package"
binary_name = "replace-me-binary"
```

Go module 使用语法有效且醒目的默认值：

```toml
go_module = "example.invalid/replace-me-module"
```

Export metadata 不复用 `instantiation.validation.metadata`。Validation metadata 只服务 disposable staging validation；export metadata 是面向使用者的稳定默认值，两者拥有不同的变更原因和审查边界。

导出过程执行完整 project instantiation，使 JSON、TOML 等派生字符串得到正确转义，Rust crate identifier 等派生名称保持一致，包含 metadata token 的路径也被安全替换。候选树中不应残留已声明的 uppercase metadata token。

## 值解析顺序

Capability 与 metadata 分别从 template profile 和 export metadata 开始，再应用 CLI 输入；交互模式最后编辑当前值。

```text
profile capability defaults / template export metadata
    -> CLI inputs
    -> interactive edits
```

Capability 的 CLI enable/disable 是最终显式选择，交互中跳过对应问题。Metadata CLI 参数进入可编辑的当前值，交互回答可以替换它们；非交互模式则直接使用 CLI 结果。

## Destination 安全

Destination 不需要是 Git 仓库，但必须不存在或为空。非空 destination 明确失败；第一版不提供 `--force`。

渲染应先进入 destination 同级的隔离 staging，所有合同验证、capability resolution、metadata validation、render 和 project instantiation 成功后再原子发布。失败或取消时 destination 保持原状。

导出完整实例化树，不应用已有项目的 protected path 列表。工具不向树中加入 manifest、说明文件或其他非模板输出，避免这些文件被误认为 template deliverable 的一部分。

候选树仍然处于 unbootstrapped template 状态。命令不生成 mise、Go、Cargo、pnpm 锁定状态或 GitHub Action digest，也不运行项目检查。

## 输出

成功输出至少包含：

```text
Repository: https://github.com/YewFence/template.git
Template: rust
Ref: main
Template-Commit: <commit>
Capabilities: docs-site
Destination: /absolute/path/to/rust-template-main
```

输出还应提示候选树只供人工比较和选择性复制，不表示现有项目已经更新，也不包含 dependency bootstrap 状态。

## 实现边界

实现复用 `SelectedTemplate.prepare()` 和 `prepare_template()`，不复制 renderer、capability resolver 或 instantiation 逻辑。Selected-ref bootstrap 必须像 `apply-template`、`init-project` 和 capability discovery 一样，使用目标 ref 自己的锁定工具环境执行 `template-tool export`。

## 验证

至少覆盖以下行为：

- selected-ref engine dispatch 与 locked uv 环境；
- 交互一路接受默认值可以成功导出；
- 交互只修改部分 metadata；
- 非交互模式使用完整 export metadata；
- CLI 与交互的解析顺序；
- selected ref 新增字段时使用 profile 或 export default；
- capability-owned outputs 与 effective capability set 一致；
- JSON、TOML、派生 identifier 和路径 token 被正确实例化；
- 输出树不残留已声明的 uppercase metadata token；
- destination 非空、合同无效、取消或实例化失败时不修改 destination；
- 命令不要求或修改 Git repository，不生成 `.git`；
- 输出树不包含工具额外生成的 manifest 或说明文件。

## 完成条件

- `export-template` 与 `template-tool export` 使用 selected-ref engine；
- 三个 template profile 都声明并验证完整 export metadata；
- 交互、非交互和 destination 安全行为由测试覆盖；
- README 增加面向使用者的导出示例与边界说明；
- 当前架构文档在实现完成后加入 Template export 生命周期；
- ADR 0005 和 ADR 0006 的入口描述在必要时更新，但不把 Template export 描述成项目更新协议；
- 完整工具测试、`mise run sync:check` 和受影响 template validation 通过。

## 暂不包含

- 自动比较候选树与现有项目；
- 自动选择、复制、合并或删除文件；
- 扫描现有项目并推断 metadata；
- 在项目中记录 template ref、commit 或 provenance；
- 重复 apply、自动升级、更新 PR 或冲突解决协议；
- dependency bootstrap、锁文件生成或项目检查；
- 覆盖非空 destination 的 `--force` 模式。
