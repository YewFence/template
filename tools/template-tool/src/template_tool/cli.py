from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .application import (
    DEFAULT_REPOSITORY,
    ApplicationError,
    ApplyResult,
    apply_template,
)
from .actions import update_actions
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
    parser.add_argument(
        "--check", action="store_true", help="compare generated output without writing"
    )
    _root_argument(parser)
    return parser


def render_main(argv: list[str] | None = None) -> None:
    args = _render_parser().parse_args(argv)
    try:
        repository = TemplateRepository(args.root)
        failed = False
        root_result = (
            repository.check_repository()
            if args.check
            else repository.render_repository()
        )
        if root_result.matches:
            action = "in sync" if args.check else "rendered"
            print(f"repository: {action}")
        else:
            failed = True
            print("repository: generated output differs", file=sys.stderr)
            for difference in root_result.differences:
                print(difference, file=sys.stderr)
        for template in repository.select(args.template):
            try:
                result = (
                    repository.check(template)
                    if args.check
                    else repository.render(template)
                )
            except TemplateError as error:
                failed = True
                print(f"{template}: {error}", file=sys.stderr)
                continue

            if result.matches:
                action = "in sync" if args.check else "rendered"
                print(f"{template}: {action}")
                continue

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
            print(f"{template}: running mise run check")
            try:
                _run_template_project_check(repository, template)
            except TemplateError as error:
                failed = True
                print(f"{template}: {error}", file=sys.stderr)

        for template in names:
            result = repository.check(template)
            if not result.matches:
                failed = True
                print(
                    f"{template}: template check modified generated files",
                    file=sys.stderr,
                )
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
    template_root = repository.templates_root / template
    with tempfile.TemporaryDirectory(prefix=f"template-check-{template}-") as temporary:
        git_dir = Path(temporary) / "repo.git"
        index = Path(temporary) / "index"
        subprocess.run(["git", "init", "--bare", "--quiet", str(git_dir)], check=True)
        subprocess.run(
            ["git", "--git-dir", str(git_dir), "config", "core.bare", "false"],
            check=True,
        )
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
        subprocess.run(
            ["git", "add", "--force", "--all"],
            cwd=template_root,
            env=template_environment,
            check=True,
        )
        tree = subprocess.run(
            ["git", "write-tree"],
            cwd=template_root,
            env=template_environment,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "commit-tree", tree, "-m", "template check baseline"],
            cwd=template_root,
            env=template_environment,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "update-ref", "HEAD", commit],
            cwd=template_root,
            env=template_environment,
            check=True,
        )
        git_marker = template_root / ".git"
        if os.path.lexists(git_marker):
            raise TemplateError(f"generated template unexpectedly contains .git: {template_root}")
        git_marker.write_text(f"gitdir: {git_dir}\n", encoding="utf-8")
        try:
            check_environment = environment | {"MISE_TRUSTED_CONFIG_PATHS": str(template_root)}
            subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=template_root,
                env=check_environment,
                check=True,
                text=True,
                capture_output=True,
            )
            completed = subprocess.run(
                ["mise", "run", "check"],
                cwd=template_root,
                env=check_environment,
                check=False,
            )
        finally:
            git_marker.unlink()
    if completed.returncode != 0:
        raise TemplateError(f"mise run check exited with {completed.returncode}")


def _locks_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="locks-update")
    parser.add_argument("template", help="template name")
    parser.add_argument("--bump", action="store_true", help="re-resolve fuzzy mise versions")
    _root_argument(parser)
    return parser


def locks_main(argv: list[str] | None = None) -> None:
    args = _locks_parser().parse_args(argv)
    try:
        repository = TemplateRepository(args.root)
        names = repository.select(args.template)
        if len(names) != 1:
            raise TemplateError("locks-update requires exactly one template")
        template = names[0]
        overlay_root = repository.overlays_root / template

        def run_adapter(staging: Path, bump: bool) -> None:
            environment = os.environ.copy()
            environment.update(
                {
                    "MISE_CEILING_PATHS": str(repository.root),
                    "MISE_GLOBAL_CONFIG_FILE": "/dev/null",
                    "MISE_TRUSTED_CONFIG_PATHS": f"{overlay_root}:{staging}",
                }
            )
            command = ["mise", "run", "locks:update"]
            if bump:
                command.append("--bump")
            command.append(str(staging))
            completed = subprocess.run(
                command,
                cwd=overlay_root,
                env=environment,
                check=False,
            )
            if completed.returncode != 0:
                raise TemplateError(
                    f"overlay locks:update exited with {completed.returncode}"
                )

        print(f"{template}: updating native dependency state")
        repository.update_locks(
            template,
            args.bump,
            run_adapter,
            validate=lambda name: _run_template_project_check(repository, name),
        )
        print(f"{template}: locks updated")
    except TemplateError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        print(f"command failed with exit code {error.returncode}: {error.cmd}", file=sys.stderr)
        raise SystemExit(1) from error


def _apply_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apply-template")
    parser.add_argument("target", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPOSITORY,
        help=f"Git repository containing templates (default: {DEFAULT_REPOSITORY})",
    )
    parser.add_argument("--ref", default="main", help="Git ref to fetch")
    parser.add_argument("--template", required=True, help="template name")
    return parser


def apply_main(argv: list[str] | None = None) -> None:
    args = _apply_parser().parse_args(argv)
    try:
        result = apply_template(args.repo, args.ref, args.template, args.target)
    except ApplicationError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() if isinstance(error.stderr, str) else ""
        detail = f": {message}" if message else ""
        print(
            f"error: command failed with exit code {error.returncode}: {error.cmd}{detail}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error

    _print_apply_result(result)
    if result.conflicted:
        raise SystemExit(1)


def _actions_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="actions-update")
    _root_argument(parser)
    return parser


def actions_main(argv: list[str] | None = None) -> None:
    args = _actions_parser().parse_args(argv)
    try:
        repository = TemplateRepository(args.root)

        def run_pinact(paths: tuple[Path, ...]) -> None:
            subprocess.run(
                ["pinact", "run", "--update", *(str(path) for path in paths)],
                cwd=repository.root,
                check=True,
            )

        changed = update_actions(repository, run_pinact)
        if changed:
            for path in changed:
                print(f"updated: {path}")
        else:
            print("GitHub Action sources are already current")
    except TemplateError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        print(f"command failed with exit code {error.returncode}: {error.cmd}", file=sys.stderr)
        raise SystemExit(1) from error


def _print_apply_result(result: ApplyResult) -> None:
    print(f"Repository: {result.repository}")
    print(f"Template: {result.template}")
    print(f"Ref: {result.reference}")
    print(f"Template-Commit: {result.commit}")
    if result.skipped:
        print(f"HINT: skipped protected root paths: {', '.join(result.skipped)}")
    for hint in result.hints:
        print(f"HINT: {hint}")
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
    locks_parser = subparsers.add_parser("locks-update")
    locks_parser.add_argument("template")
    locks_parser.add_argument("--bump", action="store_true")
    _root_argument(locks_parser)
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("target", nargs="?", type=Path, default=Path.cwd())
    apply_parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    apply_parser.add_argument("--ref", default="main")
    apply_parser.add_argument("--template", required=True)
    actions_parser = subparsers.add_parser("actions-update")
    _root_argument(actions_parser)
    args = parser.parse_args(argv)

    if args.command == "apply":
        apply_main(
            [
                str(args.target),
                "--repo",
                args.repo,
                "--ref",
                args.ref,
                "--template",
                args.template,
            ]
        )
        return
    if args.command == "actions-update":
        actions_main(["--root", str(args.root)])
        return

    forwarded = []
    if args.template:
        forwarded.append(args.template)
    if getattr(args, "check", False):
        forwarded.append("--check")
    forwarded.extend(["--root", str(args.root)])
    if args.command == "render":
        render_main(forwarded)
    elif args.command == "check":
        check_main(forwarded)
    elif args.command == "locks-update":
        locks_main([args.template, *(["--bump"] if args.bump else []), "--root", str(args.root)])
