# Repository tracker: GitHub

> This is a small repository-specific contract, not a complete `gh` manual. If exact usage is unclear or a command fails, run the narrowest relevant `gh ... --help`; never guess flags or fields.

- **Repository:** `YewFence/template`
- **GitHub Projects:** unsupported; no Project is configured for this repository.
- **Pull Requests as a triage surface:** no

Use `-R "YewFence/template"` so Issue and Pull Request operations are explicitly scoped.

## Common operations

```bash
gh issue view NUMBER -R "YewFence/template" --comments --json number,title,state,body,labels,assignees,comments,parent,subIssues,blockedBy,blocking
gh issue list -R "YewFence/template" --state open --json number,title,state,labels,assignees,parent,subIssues,blockedBy,blocking
gh pr view NUMBER -R "YewFence/template" --comments --json number,title,state,body,author,labels,assignees,comments
gh issue comment NUMBER -R "YewFence/template" --body-file -
gh issue edit NUMBER -R "YewFence/template" --add-label "LABEL"
gh issue close NUMBER -R "YewFence/template" --comment "REASON"
```

Use `--json` and `--jq` for machine-readable queries. Inspect the relevant help before requesting fields or filters not shown here.

## Repository-visible relationships

Use GitHub's native sub-issue and issue-dependency relationships. Do not duplicate parents or blockers in the body when the native relationship was created successfully.

The dependency endpoint needs the blocker's numeric database ID rather than its Issue number or GraphQL node ID:

```bash
gh api "repos/YewFence/template/issues/BLOCKER_NUMBER" --jq .id
gh api --method POST "repos/YewFence/template/issues/BLOCKED_NUMBER/dependencies/blocked_by" -F issue_id=BLOCKER_DATABASE_ID
```

Before creating sub-issue relationships or changing this call, inspect `gh api --help` and the current GitHub API documentation. Use a short body reference only when the repository does not support the native relationship.

## Shared conventions

- Fetch an Issue with its body, comments, labels, state, assignees, milestone, and relevant native parent, sub-issue, blocking, and blocked-by relationships.
- Fetch a Pull Request only when it is explicitly referenced or needed as implementation evidence; Pull Requests do not participate in repository triage.
- No repository-specific triage label mapping is configured.
- Request structured output for reads and read changed entities back after every authorized mutation.
- Never close or rewrite a source Issue or Pull Request unless the user explicitly authorizes that operation.

## Spec publication

- Publish an approved repository-visible spec as one GitHub Issue in `YewFence/template`.
- Use an explicitly supplied Issue number as the stable update identity; otherwise search for an unambiguous existing spec before creating one.
- GitHub Project or feature-container attachment is unsupported because no GitHub Project is configured.
- Preserve comments and native relationships when updating an existing spec Issue.
- Do not apply implementation-ready triage state to a spec Issue.
