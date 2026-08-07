from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import questionary

from .application import (
    DEFAULT_REPOSITORY,
    ApplicationError,
    ApplyResult,
    apply_template,
    initialize_project,
    required_metadata,
    validate_apply_target,
)
from .instantiation import InstantiationError, validate_metadata_value
from .repository import TemplateError, TemplateRepository


def _root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="monorepo root containing templates.toml",
    )


def _render_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="render-template")
    parser.add_argument("template", nargs="?", help="template name; defaults to all")
    parser.add_argument("--check", action="store_true", help="compare generated output without writing")
    _root_argument(parser)
    return parser


def render_main(argv: list[str] | None = None) -> None:
    args = _render_parser().parse_args(argv)
    try:
        repository = TemplateRepository(args.root)
        failed = False
        root_result = repository.check_repository() if args.check else repository.render_repository()
        if root_result.matches:
            print(f"repository: {'in sync' if args.check else 'rendered'}")
        else:
            failed = True
            print("repository: generated output differs", file=sys.stderr)
            for difference in root_result.differences:
                print(difference, file=sys.stderr)
        for template in repository.select(args.template):
            try:
                result = repository.check(template) if args.check else repository.render(template)
            except TemplateError as error:
                failed = True
                print(f"{template}: {error}", file=sys.stderr)
                continue
            if result.matches:
                print(f"{template}: {'in sync' if args.check else 'rendered'}")
            else:
                failed = True
                print(f"{template}: generated output differs", file=sys.stderr)
                for difference in result.differences:
                    print(difference, file=sys.stderr)
        if failed:
            raise SystemExit(1)
    except TemplateError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        print(f"command failed with exit code {error.returncode}: {error.cmd}", file=sys.stderr)
        raise SystemExit(1) from error


def _check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="check-templates")
    parser.add_argument("template", nargs="?", help="template name; defaults to all")
    _root_argument(parser)
    return parser


def check_main(argv: list[str] | None = None) -> None:
    args = _check_parser().parse_args(argv)
    try:
        repository = TemplateRepository(args.root)
        names = repository.select(args.template)
        failed = False
        root_result = repository.check_repository()
        if not root_result.matches:
            failed = True
            print("repository: generated output differs", file=sys.stderr)
            for difference in root_result.differences:
                print(difference, file=sys.stderr)
        for template in names:
            result = repository.check(template)
            if not result.matches:
                failed = True
                print(f"{template}: generated output differs", file=sys.stderr)
                for difference in result.differences:
                    print(difference, file=sys.stderr)
        if failed:
            raise SystemExit(1)

        for template in names:
            print(f"{template}: running disposable staging validation")
            try:
                _run_template_project_check(repository, template)
            except TemplateError as error:
                failed = True
                print(f"{template}: {error}", file=sys.stderr)
        if failed:
            raise SystemExit(1)
    except TemplateError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        print(f"command failed with exit code {error.returncode}: {error.cmd}", file=sys.stderr)
        raise SystemExit(1) from error


def _run_template_project_check(repository: TemplateRepository, template: str) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "MISE_CEILING_PATHS": str(repository.root),
            "MISE_GLOBAL_CONFIG_FILE": "/dev/null",
            "MISE_LOCKED": "1",
            "MISE_TASK_RUN_AUTO_INSTALL": "false",
            "RUSTFLAGS": "",
        }
    )
    with tempfile.TemporaryDirectory(prefix=f"template-check-{template}-") as temporary:
        template_root = Path(temporary) / template
        shutil.copytree(repository.templates_root / template, template_root, symlinks=True)
        repository.instantiate(template, template_root, repository.validation_metadata(template))

        git_dir = Path(temporary) / "repo.git"
        index = Path(temporary) / "index"
        subprocess.run(["git", "init", "--bare", "--quiet", str(git_dir)], check=True)
        subprocess.run(["git", "--git-dir", str(git_dir), "config", "core.bare", "false"], check=True)
        subprocess.run(
            ["git", "--git-dir", str(git_dir), "config", "core.worktree", str(template_root)],
            check=True,
        )
        template_environment = environment | {
            "GIT_AUTHOR_EMAIL": "template-tool@localhost",
            "GIT_AUTHOR_NAME": "template-tool",
            "GIT_COMMITTER_EMAIL": "template-tool@localhost",
            "GIT_COMMITTER_NAME": "template-tool",
            "GIT_DIR": str(git_dir),
            "GIT_INDEX_FILE": str(index),
            "GIT_WORK_TREE": str(template_root),
            "MISE_TRUSTED_CONFIG_PATHS": str(template_root),
        }
        subprocess.run(["git", "add", "--all"], cwd=template_root, env=template_environment, check=True)
        tree = subprocess.run(
            ["git", "write-tree"], cwd=template_root, env=template_environment, check=True,
            text=True, capture_output=True,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "commit-tree", tree, "-m", "template check baseline"],
            cwd=template_root, env=template_environment, check=True, text=True, capture_output=True,
        ).stdout.strip()
        subprocess.run(["git", "update-ref", "HEAD", commit], cwd=template_root, env=template_environment, check=True)
        if os.path.lexists(template_root / ".git"):
            raise TemplateError(f"generated template unexpectedly contains .git: {template_root}")

        overlay_root = repository.overlays_root / template
        check_environment = template_environment | {
            "MISE_TRUSTED_CONFIG_PATHS": f"{overlay_root}:{template_root}"
        }
        completed = subprocess.run(
            ["mise", "run", "check", str(template_root)],
            cwd=overlay_root,
            env=check_environment,
            check=False,
        )
    if completed.returncode != 0:
        raise TemplateError(f"overlay check exited with {completed.returncode}")


def _apply_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apply-template")
    parser.add_argument("target", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--ref", required=True, help="Git ref to fetch")
    parser.add_argument("--template", required=True, help="template name")
    _metadata_arguments(parser)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--interactive", action="store_true")
    mode.add_argument("--keep-tokens", action="store_true")
    return parser


def apply_main(argv: list[str] | None = None) -> None:
    args = _apply_parser().parse_args(argv)
    metadata = _metadata_from_args(args)
    try:
        if args.keep_tokens and metadata:
            raise ApplicationError("--keep-tokens cannot be combined with metadata")
        validate_apply_target(args.target)
        if args.interactive:
            metadata = _collect_metadata(args.repo, args.ref, args.template, metadata)
        result = apply_template(
            args.repo,
            args.ref,
            args.template,
            args.target,
            metadata=None if args.keep_tokens else metadata,
            keep_tokens=args.keep_tokens,
        )
    except ApplicationError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() if isinstance(error.stderr, str) else ""
        detail = f": {message}" if message else ""
        print(f"error: command failed with exit code {error.returncode}: {error.cmd}{detail}", file=sys.stderr)
        raise SystemExit(1) from error
    _print_apply_result(result)
    if result.conflicted:
        raise SystemExit(1)


def _init_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="init-project")
    parser.add_argument("target", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--ref", required=True, help="Git ref to fetch")
    parser.add_argument("--template", required=True, help="template name")
    _metadata_arguments(parser)
    parser.add_argument("--interactive", action="store_true")
    return parser


def _metadata_arguments(parser: argparse.ArgumentParser) -> None:
    for option in (
        "project-name",
        "description",
        "github-owner",
        "repo-name",
        "go-module",
        "cargo-package",
        "binary-name",
    ):
        parser.add_argument(f"--{option}")


def _metadata_from_args(args: argparse.Namespace) -> dict[str, str]:
    return {
        key: value
        for key, value in {
            "project_name": args.project_name,
            "description": args.description,
            "github_owner": args.github_owner,
            "repo_name": args.repo_name,
            "go_module": args.go_module,
            "cargo_package": args.cargo_package,
            "binary_name": args.binary_name,
        }.items()
        if value is not None
    }


def _collect_metadata(
    repository: str,
    reference: str,
    template: str,
    provided: dict[str, str],
) -> dict[str, str]:
    required = required_metadata(repository, reference, template)
    missing = [field for field in required if field not in provided]
    metadata = dict(provided)
    try:
        for field in missing:
            while True:
                value = questionary.text(field.replace("_", " ").title()).ask()
                if value is None:
                    raise ApplicationError("interactive metadata collection cancelled")
                try:
                    validate_metadata_value(field, value)
                except InstantiationError as error:
                    print(f"error: {error}", file=sys.stderr)
                    continue
                metadata[field] = value
                break
        summary = "\n".join(f"{field}: {metadata[field]}" for field in required)
        confirmed = questionary.confirm(f"Confirm metadata?\n{summary}", default=True).ask()
        if confirmed is not True:
            raise ApplicationError("interactive metadata collection cancelled")
    except (KeyboardInterrupt, EOFError):
        raise ApplicationError("interactive metadata collection cancelled") from None
    return metadata


def init_main(argv: list[str] | None = None) -> None:
    args = _init_parser().parse_args(argv)
    metadata = _metadata_from_args(args)
    try:
        if args.interactive:
            metadata = _collect_metadata(args.repo, args.ref, args.template, metadata)
        result = initialize_project(args.repo, args.ref, args.template, args.target, metadata)
    except ApplicationError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() if isinstance(error.stderr, str) else ""
        detail = f": {message}" if message else ""
        print(f"error: command failed with exit code {error.returncode}: {error.cmd}{detail}", file=sys.stderr)
        raise SystemExit(1) from error
    print(f"Initial-Commit: {result.initial_commit}")
    _print_apply_result(result.application)
    if result.application.conflicted:
        raise SystemExit(1)


def _print_apply_result(result: ApplyResult) -> None:
    print(f"Repository: {result.repository}")
    print(f"Template: {result.template}")
    print(f"Ref: {result.reference}")
    print(f"Template-Commit: {result.commit}")
    if result.skipped:
        print(f"HINT: skipped protected root paths: {', '.join(result.skipped)}")
    for hint in result.hints:
        print(f"HINT: {hint}")
    if not result.instantiated:
        print("HINT: applied files are an uninstantiated template blueprint; review every metadata token before committing.")
        print("HINT: inspect staged tokens with `git grep --cached -nE '\\{\\{[A-Z][A-Z0-9_]*\\}\\}'`.")
    if result.conflicted:
        print("HINT: the squash merge has conflicts; Git preserved the index stages and worktree.")
        print("HINT: inspect with `git status` and `git diff`.")
        print("HINT: resolve files, run `git add`, then run `git diff --check` before committing.")
        print("HINT: cancel the entire application with `git reset --hard HEAD`.")
    else:
        print("HINT: review the staged template changes with `git status` and `git diff --cached`.")
        print("HINT: run `git diff --check` before creating your commit.")
        print("HINT: cancel the entire application with `git reset --hard HEAD`.")
    if result.jujutsu:
        print("HINT: finish, resolve, or cancel this Git application before continuing normal jj operations.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="template-tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("template", nargs="?")
    render_parser.add_argument("--check", action="store_true")
    _root_argument(render_parser)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("template", nargs="?")
    _root_argument(check_parser)
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("target", nargs="?", type=Path, default=Path.cwd())
    apply_parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    apply_parser.add_argument("--ref", required=True)
    apply_parser.add_argument("--template", required=True)
    _metadata_arguments(apply_parser)
    apply_mode = apply_parser.add_mutually_exclusive_group()
    apply_mode.add_argument("--interactive", action="store_true")
    apply_mode.add_argument("--keep-tokens", action="store_true")
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("target", nargs="?", type=Path, default=Path.cwd())
    init_parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    init_parser.add_argument("--ref", required=True)
    init_parser.add_argument("--template", required=True)
    _metadata_arguments(init_parser)
    init_parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "apply":
        forwarded = [str(args.target), "--repo", args.repo, "--ref", args.ref, "--template", args.template]
        for option in ("project-name", "description", "github-owner", "repo-name", "go-module", "cargo-package", "binary-name"):
            value = getattr(args, option.replace("-", "_"))
            if value is not None:
                forwarded.extend([f"--{option}", value])
        if args.interactive:
            forwarded.append("--interactive")
        if args.keep_tokens:
            forwarded.append("--keep-tokens")
        apply_main(forwarded)
        return
    if args.command == "init":
        forwarded = [str(args.target), "--repo", args.repo, "--ref", args.ref, "--template", args.template]
        for option in ("project-name", "description", "github-owner", "repo-name", "go-module", "cargo-package", "binary-name"):
            value = getattr(args, option.replace("-", "_"))
            if value is not None:
                forwarded.extend([f"--{option}", value])
        if args.interactive:
            forwarded.append("--interactive")
        init_main(forwarded)
        return
    forwarded = []
    if args.template:
        forwarded.append(args.template)
    if getattr(args, "check", False):
        forwarded.append("--check")
    forwarded.extend(["--root", str(args.root)])
    if args.command == "render":
        render_main(forwarded)
    else:
        check_main(forwarded)
