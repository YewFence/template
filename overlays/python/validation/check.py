from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPOSITORY_ROOT / "tools/template-tool/src"))

from template_tool.staging_validation import (  # noqa: E402
    StagingContext,
    ValidationError,
    validate_codecov_upload,
    validate_docs_site,
)


def _validate_python_contract(context: StagingContext) -> None:
    for tool in ("python", "uv", "ruff", "ty"):
        context.assert_tool(tool, message="Python mise tool is missing")
    context.assert_tasks(
        (
            "deps:check",
            "deps:fix",
            "deps:update",
            "test",
            "fmt:check",
            "fmt:fix",
            "lint",
            "lint:fix",
            "build",
            "build:check",
        ),
        message="Python mise task is missing",
    )
    context.assert_tasks(("audit",), message="Python CI mise task is missing", ci=True)
    context.assert_contains(
        "pyproject.toml",
        (
            "[project]",
            "[dependency-groups]",
            "[build-system]",
            "src/example_python_project",
        ),
        message="Python project metadata is incomplete",
    )
    if not context.exists("src/example_python_project/__init__.py"):
        raise ValidationError("Python package source is missing")
    if not context.exists("tests/test_package.py"):
        raise ValidationError("Python smoke test is missing")

    pyproject = tomllib.loads(context.read("pyproject.toml"))
    has_coverage_dependency = "pytest-cov>=7,<8" in pyproject["dependency-groups"].get(
        "coverage", []
    )
    if context.has_capability("codecov-upload") != has_coverage_dependency:
        raise ValidationError("Python coverage dependency does not match codecov-upload")


def validate(context: StagingContext) -> None:
    _validate_python_contract(context)
    validate_docs_site(context)
    validate_codecov_upload(
        context,
        coverage_report="coverage.xml",
        forbidden_coverage_tools=(r"cargo-llvm-cov", r"golang\.org/.*/cover"),
        required_ci_tools=('"pipx:codecov-cli" = "11"',),
    )

    context = context.with_environment(MISE_LOCKED=None)
    context.mise("-C", str(context.template_root), "-E", "ci", "lock")
    context = context.with_environment(MISE_LOCKED="1")
    context.mise("-C", str(context.template_root), "-E", "ci", "install", "--locked")
    context.mise("-C", str(context.template_root), "run", "deps:update")
    if context.has_capability("docs-site"):
        context.mise("-C", str(context.template_root), "run", "docs:lock")
        context.mise("-C", str(context.template_root), "run", "docs:build")
    context.mise("-C", str(context.template_root), "-E", "ci", "run", "audit")
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
            arguments[0], allowed_capabilities=("codecov-upload", "docs-site")
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
