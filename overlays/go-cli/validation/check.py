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


def _require_text(text: str, required: tuple[str, ...], *, message: str) -> None:
    for value in required:
        if value not in text:
            raise ValidationError(f"{message}: {value}")


def _require_no_match(text: str, pattern: str, *, message: str) -> None:
    if re.search(pattern, text, re.MULTILINE):
        raise ValidationError(message)


def _validate_container_image_publish(context: StagingContext) -> None:
    """Validate the Go CLI-specific container capability contract."""
    enabled = context.has_capability("container-image-publish")
    ci_tasks = context.task_names(ci=True)
    ci_tools = context.read("mise.ci.toml")
    release_workflow = context.read(".github/workflows/release.yml")

    if enabled:
        context.assert_tasks(
            ("container:build", "container:publish"),
            ci=True,
            message="container-image-publish enabled but mise task is missing",
        )
        if not re.search(
            r'^"aqua:ko-build/ko"\s*=\s*"0\.19"$', ci_tools, re.MULTILINE
        ):
            raise ValidationError("container-image-publish enabled but ko tool is missing")
        _require_text(
            ci_tools,
            (
                "./cmd/example-go-cli",
                "ko build --local --tags dev",
                "--platform=all",
                "--bare",
            ),
            message="container-image-publish enabled but ko task contract is incomplete",
        )
        _require_text(
            release_workflow,
            (
                "  publish-container:",
                "needs: [version, release]",
                "packages: write",
                "ko login ghcr.io",
                "CONTAINER_IMAGE_REPOSITORY: ghcr.io/YewFence/example-go-cli",
                "RELEASE_PRERELEASE: ${{ needs.version.outputs.prerelease }}",
                "run: mise run container:publish",
            ),
            message="container-image-publish enabled but release workflow contract is incomplete",
        )
        _require_no_match(
            release_workflow,
            r"ko build",
            message="container-image-publish workflow duplicates the ko build command",
        )
        _require_text(
            ci_tools,
            (
                "tag_args+=(--tags latest)",
                "RELEASE_PRERELEASE must be true or false",
            ),
            message="container-image-publish enabled but stable and prerelease tag branches are missing",
        )
    else:
        if "container:build" in ci_tasks or "container:publish" in ci_tasks:
            raise ValidationError("container-image-publish disabled but mise task remains")
        _require_no_match(
            ci_tools,
            r'^"aqua:ko-build/ko"\s*=',
            message="container-image-publish disabled but ko tool remains",
        )
        _require_no_match(
            release_workflow,
            r"publish-container|ko login ghcr\.io|packages: write|CONTAINER_IMAGE_REPOSITORY: ghcr\.io/",
            message="container-image-publish disabled but release workflow behavior remains",
        )

    for unexpected_output in ("Dockerfile", "ko.yaml", ".ko.yaml"):
        if context.exists(unexpected_output):
            raise ValidationError(
                f"container-image-publish must not generate {unexpected_output}"
            )


def validate(context: StagingContext) -> None:
    legacy = context.git(
        "-C",
        str(context.template_root),
        "grep",
        "-nE",
        r"(your-cli|github\.com/example/your-cli|README\.template\.md|AGENTS\.template\.md|tools/(init-template|apply-existing))",
        "--",
        ".",
        check=False,
    )
    if legacy.returncode == 0:
        raise ValidationError("legacy Go CLI identity remains in staging")
    if legacy.returncode != 1:
        raise ValidationError(f"git identity check failed with exit code {legacy.returncode}")

    validate_docs_site(context)
    validate_codecov_upload(
        context,
        coverage_report="coverage.out",
        required_ci_tools=('"pipx:codecov-cli" = "11"',),
    )
    _validate_container_image_publish(context)

    context = context.with_environment(MISE_LOCKED=None)
    context.mise("-C", str(context.template_root), "-E", "ci", "lock")
    context = context.with_environment(MISE_LOCKED="1")
    context.mise("-C", str(context.template_root), "-E", "ci", "install", "--locked")
    context.mise("-C", str(context.template_root), "run", "deps:update")
    if context.has_capability("container-image-publish"):
        context.mise("-C", str(context.template_root), "-E", "ci", "run", "container:build")
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
            arguments[0],
            allowed_capabilities=("codecov-upload", "container-image-publish", "docs-site"),
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
