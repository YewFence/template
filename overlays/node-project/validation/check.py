from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPOSITORY_ROOT / "tools/template-tool/src"))

from template_tool.staging_validation import (  # noqa: E402
    StagingContext,
    ValidationError,
    validate_codecov_upload,
    validate_docs_site,
)


def _validate_node_contract(context: StagingContext) -> None:
    for tool in ("node", "aube"):
        context.assert_tool(tool, message="Node mise tool is missing")
    context.assert_tasks(
        (
            "deps:check",
            "deps:fix",
            "deps:update",
            "deps:install",
            "test",
            "fmt:check",
            "fmt:fix",
            "lint",
            "lint:fix",
            "build",
            "build:check",
        ),
        message="Node mise task is missing",
    )
    context.assert_tasks(("audit",), message="Node CI mise task is missing", ci=True)
    context.assert_contains(
        "package.json",
        (
            '"type": "module"',
            '"exports"',
            '"devDependencies"',
            '"oxlint"',
            '"oxfmt"',
            '"tsdown"',
            '"typescript"',
            '"vitest"',
        ),
        message="Node project metadata is incomplete",
    )
    if not context.exists("src"):
        raise ValidationError("Node package source is missing")
    if not context.exists("tests/index.test.ts"):
        raise ValidationError("Node smoke test is missing")
    if not context.exists("tsconfig.json") or not context.exists("vitest.config.ts"):
        raise ValidationError("Node TypeScript configuration is missing")

    package = json.loads(context.read("package.json"))
    dev_dependencies = package.get("devDependencies", {})
    has_coverage_dependency = "@vitest/coverage-v8" in dev_dependencies
    if context.has_capability("codecov-upload") != has_coverage_dependency:
        raise ValidationError("Node coverage dependency does not match codecov-upload")


def _validate_npm_publish(context: StagingContext) -> None:
    enabled = context.has_capability("npm-publish")
    ci_tasks = context.task_names(ci=True)
    ci_workflow = context.read(".github/workflows/ci.yml")
    release_workflow = context.read(".github/workflows/release.yml")

    if enabled:
        for task in ("npm:package:check", "npm:publish"):
            if task not in ci_tasks:
                raise ValidationError(
                    f"npm-publish enabled but mise task is missing: {task}"
                )
        script = context.template_root / "scripts/publish-npm"
        if not script.is_file() or not script.stat().st_mode & 0o111:
            raise ValidationError("npm-publish enabled but executable publish script is missing")
        if "run: mise run npm:package:check" not in ci_workflow:
            raise ValidationError("npm-publish enabled but CI package check step is missing")
        if "run: mise run npm:publish" not in release_workflow:
            raise ValidationError("npm-publish enabled but release publish step is missing")
    else:
        for task in ("npm:package:check", "npm:publish"):
            if task in ci_tasks:
                raise ValidationError(f"npm-publish disabled but mise task remains: {task}")
        if context.exists("scripts/publish-npm"):
            raise ValidationError("npm-publish disabled but publish script remains")
        if "run: mise run npm:package:check" in ci_workflow:
            raise ValidationError("npm-publish disabled but CI package check step remains")
        if "run: mise run npm:publish" in release_workflow:
            raise ValidationError("npm-publish disabled but release publish step remains")


def validate(context: StagingContext) -> None:
    _validate_node_contract(context)
    _validate_npm_publish(context)
    validate_docs_site(context, docs_tools=("node", "aube"), docs_only_tools=())
    validate_codecov_upload(
        context,
        coverage_report="coverage/lcov.info",
        forbidden_coverage_tools=(r"cargo-llvm-cov", r"golang\.org/.*/cover"),
        required_ci_tools=('"pipx:codecov-cli" = "11"',),
    )

    context = context.with_environment(MISE_LOCKED=None)
    context.mise("-C", str(context.template_root), "-E", "ci", "lock")
    context = context.with_environment(MISE_LOCKED="1")
    context.mise("-C", str(context.template_root), "-E", "ci", "install", "--locked")
    context.mise("-C", str(context.template_root), "run", "deps:update")
    context.mise("-C", str(context.template_root), "run", "deps:install")
    if context.has_capability("docs-site"):
        context.mise("-C", str(context.template_root), "run", "docs:lock")
        context.mise("-C", str(context.template_root), "run", "docs:build")
    context.mise("-C", str(context.template_root), "-E", "ci", "run", "audit")
    if context.has_capability("npm-publish"):
        context.mise("-C", str(context.template_root), "-E", "ci", "run", "npm:package:check")
    context.mise("-C", str(context.template_root), "run", "actions:update")
    context.git("-C", str(context.template_root), "add", "--all")
    context.mise("-C", str(context.template_root), "run", "check")


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: check.py <template_root>", file=sys.stderr)
        return 2
    try:
        context = StagingContext.from_environment(
            arguments[0], allowed_capabilities=("codecov-upload", "docs-site", "npm-publish")
        )
        validate(context)
    except (ValidationError, OSError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            print(f"command failed with exit code {error.returncode}: {error.cmd}", file=sys.stderr)
        else:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
