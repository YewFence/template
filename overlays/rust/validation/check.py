from __future__ import annotations

import re
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


def _validate_crates_io_publish(context: StagingContext) -> None:
    """Validate the Rust crates.io publishing capability contract."""
    enabled = context.has_capability("crates-io-publish")
    ci_tasks = context.task_names(ci=True)
    ci_tools = context.read("mise.ci.toml")
    ci_workflow = context.read(".github/workflows/ci.yml")
    release_workflow = context.read(".github/workflows/release.yml")

    if enabled:
        for task in ("crates-io:package:check", "crates-io:publish"):
            if task not in ci_tasks:
                raise ValidationError(
                    f"crates-io-publish enabled but mise task is missing: {task}"
                )
        if not re.search(r"^jq\s*=", ci_tools, re.MULTILINE):
            raise ValidationError("crates-io-publish enabled but jq tool is missing")
        script = context.template_root / "scripts/publish-crate"
        if not script.is_file() or not script.stat().st_mode & 0o111:
            raise ValidationError("crates-io-publish enabled but executable publish script is missing")
        if "run: mise run crates-io:package:check" not in ci_workflow:
            raise ValidationError("crates-io-publish enabled but CI package check step is missing")
        if "run: mise run crates-io:publish" not in release_workflow:
            raise ValidationError("crates-io-publish enabled but release publish step is missing")
    else:
        for task in ("crates-io:package:check", "crates-io:publish"):
            if task in ci_tasks:
                raise ValidationError(f"crates-io-publish disabled but mise task remains: {task}")
        if re.search(r"^jq\s*=", ci_tools, re.MULTILINE):
            raise ValidationError("crates-io-publish disabled but jq tool remains")
        if context.exists("scripts/publish-crate"):
            raise ValidationError("crates-io-publish disabled but publish script remains")
        if "run: mise run crates-io:package:check" in ci_workflow:
            raise ValidationError("crates-io-publish disabled but CI package check step remains")
        if "run: mise run crates-io:publish" in release_workflow:
            raise ValidationError("crates-io-publish disabled but release publish step remains")


def validate(context: StagingContext) -> None:
    legacy = context.git(
        "-C",
        str(context.template_root),
        "grep",
        "-nE",
        r"(rust-template|rust_template|README\.template\.md|AGENTS\.template\.md)",
        "--",
        ".",
        check=False,
    )
    if legacy.returncode == 0:
        raise ValidationError("legacy Rust identity remains in staging")
    if legacy.returncode != 1:
        raise ValidationError(f"git identity check failed with exit code {legacy.returncode}")

    validate_docs_site(context)
    validate_codecov_upload(
        context,
        coverage_report="lcov.info",
        required_ci_tools=(
            '"pipx:codecov-cli" = "11"',
            '"cargo:cargo-llvm-cov" = "0.8"',
        ),
    )
    _validate_crates_io_publish(context)

    context = context.with_environment(MISE_LOCKED=None)
    context.mise("-C", str(context.template_root), "-E", "ci", "lock")
    context = context.with_environment(MISE_LOCKED="1")
    context.mise("-C", str(context.template_root), "-E", "ci", "install", "--locked")
    context.mise("-C", str(context.template_root), "run", "deps:update")
    if context.has_capability("docs-site"):
        context.mise("-C", str(context.template_root), "run", "docs:lock")
        context.mise("-C", str(context.template_root), "run", "docs:build")
    if context.has_capability("crates-io-publish"):
        context.mise("-C", str(context.template_root), "-E", "ci", "run", "crates-io:package:check")
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
            arguments[0],
            allowed_capabilities=("codecov-upload", "crates-io-publish", "docs-site"),
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
