from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path


class ValidationError(RuntimeError):
    """Raised when a staged template violates a validation contract."""


def parse_enabled_capabilities(
    value: str | None = None,
    *,
    allowed: Sequence[str],
) -> tuple[str, ...]:
    """Parse the adapter capability environment and return a canonical set."""
    raw = os.environ.get("TEMPLATE_TOOL_ENABLED_CAPABILITIES") if value is None else value
    if raw is None:
        raise ValidationError("TEMPLATE_TOOL_ENABLED_CAPABILITIES is required")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValidationError("TEMPLATE_TOOL_ENABLED_CAPABILITIES must be a JSON array") from error
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValidationError("TEMPLATE_TOOL_ENABLED_CAPABILITIES must be a JSON array of strings")
    if len(parsed) != len(set(parsed)):
        raise ValidationError("TEMPLATE_TOOL_ENABLED_CAPABILITIES must not contain duplicates")
    unknown = sorted(set(parsed) - set(allowed))
    if unknown:
        raise ValidationError(
            "unexpected capabilities: " + ", ".join(unknown)
        )
    return tuple(sorted(parsed))


@dataclass(frozen=True)
class StagingContext:
    """Command and filesystem context shared by overlay validation adapters."""

    template_root: Path
    enabled_capabilities: tuple[str, ...]
    environment: Mapping[str, str]

    @classmethod
    def from_environment(
        cls,
        template_root: str | Path,
        *,
        allowed_capabilities: Sequence[str],
    ) -> "StagingContext":
        root = Path(template_root)
        if not root.is_dir():
            raise ValidationError(f"staging template root is not a directory: {root}")
        return cls(
            root,
            parse_enabled_capabilities(allowed=allowed_capabilities),
            dict(os.environ),
        )

    def has_capability(self, capability: str) -> bool:
        return capability in self.enabled_capabilities

    def with_environment(self, **updates: str | None) -> "StagingContext":
        environment = dict(self.environment)
        for name, value in updates.items():
            if value is None:
                environment.pop(name, None)
            else:
                environment[name] = value
        return replace(self, environment=environment)

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(self.environment),
            check=check,
            capture_output=capture_output,
            text=True,
        )

    def output(self, command: Sequence[str], *, cwd: Path | None = None) -> str:
        return self.run(command, cwd=cwd, capture_output=True).stdout

    def mise(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run(("mise", *arguments), check=check)

    def mise_output(self, *arguments: str) -> str:
        return self.output(("mise", *arguments))

    def git(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run(("git", *arguments), check=check)

    def task_names(self, *, ci: bool = False) -> frozenset[str]:
        arguments = ("-C", str(self.template_root))
        if ci:
            arguments += ("-E", "ci")
        arguments += ("tasks", "ls", "--local", "--name-only")
        return frozenset(self.mise_output(*arguments).splitlines())

    def read(self, relative_path: str) -> str:
        path = self.template_root / relative_path
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            raise ValidationError(f"required file is not readable: {relative_path}") from error

    def exists(self, relative_path: str) -> bool:
        return (self.template_root / relative_path).exists()

    def assert_tasks(self, tasks: Sequence[str], *, message: str, ci: bool = False) -> None:
        available = self.task_names(ci=ci)
        for task in tasks:
            if task not in available:
                raise ValidationError(f"{message}: {task}")

    def assert_tool(self, tool: str, *, message: str, relative_path: str = "mise.toml") -> None:
        if not re.search(rf"^{re.escape(tool)}\s*=", self.read(relative_path), re.MULTILINE):
            raise ValidationError(f"{message}: {tool}")

    def assert_contains(self, relative_path: str, required: Sequence[str], *, message: str) -> None:
        _require_text(self.read(relative_path), required, message=message)

    def assert_absent(self, relative_path: str, *, message: str) -> None:
        if self.exists(relative_path):
            raise ValidationError(message)


def _require_text(text: str, required: Sequence[str], *, message: str) -> None:
    for value in required:
        if value not in text:
            raise ValidationError(f"{message}: {value}")


def _require_no_match(text: str, pattern: str, *, message: str) -> None:
    if re.search(pattern, text, re.MULTILINE):
        raise ValidationError(message)


def _job_text(workflow: str, job: str) -> str:
    match = re.search(rf"^  {re.escape(job)}:\n(?P<body>(?:^(?!  [A-Za-z0-9_-]+:).*(?:\n|$))*)", workflow, re.MULTILINE)
    if match is None:
        raise ValidationError(f"workflow job is missing: {job}")
    return match.group("body")


def validate_docs_site(context: StagingContext) -> None:
    """Validate the shared docs-site enabled/disabled output contract."""
    workflow = context.read(".github/workflows/ci.yml")
    enabled = context.has_capability("docs-site")
    if enabled:
        context.assert_tasks(
            ("docs:install", "docs:lock", "docs:install:locked", "docs:dev", "docs:build", "docs:preview"),
            message="docs-site enabled but mise task is missing",
        )
        for tool in ("node", "pnpm"):
            context.assert_tool(tool, message="docs-site enabled but mise tool is missing")
        if not context.exists("docs") or not context.exists("docs/package.json") or not context.exists(".github/workflows/docs.yml"):
            raise ValidationError("docs-site enabled but complete outputs are missing")
        if not re.search(r"^  docs:$", workflow, re.MULTILINE) or "run: mise run docs:build" not in workflow:
            raise ValidationError("docs-site enabled but CI docs job is missing")
    else:
        if any(task.startswith("docs:") for task in context.task_names()):
            raise ValidationError("docs-site disabled but mise docs tasks remain")
        for tool in ("node", "pnpm"):
            if re.search(rf"^{re.escape(tool)}\s*=", context.read("mise.toml"), re.MULTILINE):
                raise ValidationError(f"docs-site disabled but mise tool remains: {tool}")
        if context.exists("docs") or context.exists(".github/workflows/docs.yml"):
            raise ValidationError("docs-site disabled but complete outputs remain")
        if re.search(r"^  docs:$", workflow, re.MULTILINE) or "run: mise run docs:build" in workflow:
            raise ValidationError("docs-site disabled but CI docs job remains")


def validate_codecov_upload(
    context: StagingContext,
    *,
    coverage_report: str,
    coverage_placeholder: Sequence[str] = (),
    forbidden_coverage_tools: Sequence[str] = (),
    required_ci_tools: Sequence[str] = (),
) -> None:
    """Validate the shared Codecov workflow and coverage output contract."""
    enabled = context.has_capability("codecov-upload")
    ci_workflow = context.read(".github/workflows/ci.yml")
    ci_tools = context.read("mise.ci.toml")
    gitignore = context.read(".gitignore") if context.exists(".gitignore") else ""
    coverage_workflow = context.read(".github/workflows/coverage.yml") if context.exists(".github/workflows/coverage.yml") else ""
    if enabled:
        coverage_job = _job_text(ci_workflow, "coverage")
        context.assert_tasks(("coverage",), message="codecov-upload enabled but mise coverage task is missing")
        mise = context.read("mise.toml")
        _require_text(
            mise,
            coverage_placeholder,
            message="codecov-upload enabled but coverage placeholder contract is incomplete",
        )
        _require_text(
            coverage_job,
            (
                "run: mise run coverage",
                "contents: read",
                "uses: codecov/codecov-action@v7",
                "binary: ${{ steps.codecov-cli.outputs.path }}",
                "files: ${{ steps.coverage.outputs.report }}",
                "disable_search: true",
                "fail_ci_if_error: true",
                "github.event_name ==",
                "id: codecov-cli",
                "GITHUB_STEP_SUMMARY",
            ),
            message="codecov-upload enabled but coverage job is missing",
        )
        _require_no_match(
            coverage_job,
            r"id-token: write|contents: write|packages: write|pull-requests: write|CODECOV_TOKEN|pull_request_target|use_oidc|override_branch|override_pr|skip_validation",
            message="codecov-upload coverage job requests unsafe permissions or authentication",
        )
        for tool in required_ci_tools:
            if tool not in ci_tools or tool in mise:
                raise ValidationError(f"codecov-upload CLI tool ownership is incorrect: {tool}")
        if not coverage_workflow:
            raise ValidationError("codecov-upload default branch workflow is missing")
        _require_text(
            coverage_workflow,
            (
                "github.event_name ==",
                "refs/heads/main",
                "id-token: write",
                "use_oidc: true",
                "binary: ${{ steps.codecov-cli.outputs.path }}",
                "files: ${{ steps.coverage.outputs.report }}",
                "group: coverage-${{ github.ref }}",
                "cancel-in-progress: true",
            ),
            message="codecov-upload default branch workflow is missing",
        )
        _require_no_match(
            coverage_workflow,
            r"pull_request|CODECOV_TOKEN|pull_request_target|override_branch|override_pr|skip_validation",
            message="codecov-upload default branch workflow has unsafe or PR-only behavior",
        )
        if f"/{coverage_report}" not in gitignore.splitlines():
            raise ValidationError(f"codecov-upload enabled but coverage report is not ignored: {coverage_report}")
        if any(re.search(pattern, ci_tools) for pattern in forbidden_coverage_tools):
            raise ValidationError("codecov-upload coverage tool ownership is incorrect")
    else:
        if (
            "coverage" in context.task_names()
            or re.search(r"codecov|id-token: write|mise run coverage", ci_workflow)
            or context.exists(".github/workflows/coverage.yml")
            or "pipx:codecov-cli" in ci_tools
            or f"/{coverage_report}" in gitignore.splitlines()
        ):
            raise ValidationError("codecov-upload disabled but coverage behavior remains")
