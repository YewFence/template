from __future__ import annotations

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


def validate(context: StagingContext) -> None:
    legacy = context.git(
        "-C",
        str(context.template_root),
        "grep",
        "-nE",
        r"(README\.template\.md|AGENTS\.template\.md)",
        "--",
        ".",
        check=False,
    )
    if legacy.returncode == 0:
        raise ValidationError("legacy common template identity files remain in staging")
    if legacy.returncode != 1:
        raise ValidationError(f"git identity check failed with exit code {legacy.returncode}")

    validate_docs_site(context)
    validate_codecov_upload(
        context,
        coverage_report="coverage.xml",
        coverage_placeholder=(
            "[tasks.coverage]",
            "generates coverage.xml in the repository root",
            "exit 1",
        ),
        forbidden_coverage_tools=(r"cargo-llvm-cov", r"golang\.org/.*/cover"),
        required_ci_tools=('"pipx:codecov-cli" = "11"',),
    )

    context = context.with_environment(MISE_LOCKED=None)
    context.mise("-C", str(context.template_root), "-E", "ci", "lock")
    context = context.with_environment(MISE_LOCKED="1")
    context.mise("-C", str(context.template_root), "install", "--locked")
    context.mise("-C", str(context.template_root), "run", "deps:update")
    if context.has_capability("docs-site"):
        context.mise("-C", str(context.template_root), "run", "docs:lock")
        context.mise("-C", str(context.template_root), "run", "docs:build")
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
