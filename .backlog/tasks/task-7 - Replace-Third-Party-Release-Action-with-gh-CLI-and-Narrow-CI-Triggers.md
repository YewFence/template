---
id: TASK-7
title: Replace Third-Party Release Action with gh CLI and Narrow CI Triggers
status: Done
assignee:
  - '@codex'
created_date: '2026-09-07 17:07'
updated_date: '2026-09-11 14:34'
labels: []
dependencies: []
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Outcome

模板生成 CI 的三项维护性优化：

- 以共享 gh CLI adapter（`publish-release.sh`）替换第三方 `softprops/action-gh-release`：发布、附件上传与重跑编辑分别由 `gh release create/upload/edit` 承担；构建与发布固定到解析出的 commit SHA，仅 release PR 合并入口允许自动创建 tag，发布 job 按 tag 互斥；重跑保留人工标题与额外附件，更新说明、prerelease 状态和同名附件。
- Action 版本检查从常规 CI 分离为独立 workflow，仅在 main push 或 main 手动触发时运行；普通 PR CI 保留 actionlint 与离线 pin 校验。
- 文档自动部署触发范围收窄到 `docs/**`，保留手动入口与 CI 文档构建检查。
<!-- SECTION:DESCRIPTION:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Extract Action version maintenance into a standalone workflow for main pushes and manual runs on main; preserve PR correctness checks.
2. Restrict automatic Docs deployment to docs/** while retaining workflow_dispatch.
3. Replace the third-party Release Action with a shared GitHub adapter using gh release create/upload/edit. Use read-only gh api for nullable resource discovery and exact remote tag commit checks.
4. Fix build/publication to the resolved checkout SHA; allow automatic tag creation only for merged release PRs. Serialize GitHub Release publication by tag. Remove local tag creation/push and release:tag:create.
5. Delegate initial asset publication and temporary draft cleanup to gh release create, as explicitly accepted by the user. For existing releases, upload with clobber before editing notes/prerelease or publishing drafts; preserve titles and extra assets. Use CLI default Latest behavior; propagate GitHub immutable protection and other failures without custom rollback.
6. Add offline adapter and rendering regression tests, document the final contract, regenerate all previews, and run tool tests, sync, actionlint and ShellCheck without remote publication.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented the approved Action Versions and Docs trigger changes. Action Versions is now a shared standalone workflow for main pushes and manual runs on main; PR actionlint/offline pin checks remain unchanged. Docs auto-deployment only matches docs/** and retains workflow_dispatch. Regenerated common/go-cli/rust previews. Verification: 158 tool tests passed, mise run sync:check passed, actionlint passed for all 9 affected generated workflows, and git diff --check passed. Full disposable staging validation remains delegated to GitHub Actions per repository policy.
Release workflow/task files remain unchanged. Official gh help/source confirms automatic remote tag creation when absent, with --target selecting the commit and --verify-tag disabling automatic creation. Existing implementation creates annotated tags and validates existing tag targets; replacing its push requires an explicit decision on those semantics. Release replacement remains deferred, so TASK-7 stays In Progress.

Release replacement is now implemented. User revised the earlier draft-retention decision: initial gh release create may clean up its own temporary draft on failure; existing releases are never explicitly deleted by our adapter. All publication writes use gh release commands; API calls are read-only. Exact tag refs avoid same-named branch ambiguity.
Verification: 193 tool tests passed; mise run sync:check passed for all three templates; actionlint passed for all three release workflows; ShellCheck passed for the shared publication script and all generated copies; git diff --check passed. Public GitHub read-only probes confirmed nullable GraphQL discovery and refs/tags commit lookup. Actual release mutations, uploads, and immutable enforcement were not exercised remotely; offline gh fixtures verify orchestration and error propagation. Full disposable staging validation is left to GitHub Actions per repository policy.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Completed all three optimizations: independent main-only Action Versions workflow, docs/**-only automatic Docs deployment, and gh release-based publishing with fixed commit targets, tag checks, reruns, and per-tag publication concurrency. Removed the third-party Release Action and local tag creation task, synchronized previews and architecture documentation. Verified with 193 tool tests, sync:check, actionlint, ShellCheck, and diff whitespace checks. No remote publication performed.
<!-- SECTION:FINAL_SUMMARY:END -->
