from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

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

        for template in names:
            result = repository.check(template)
            if not result.matches:
                failed = True
                print(f"{template}: generated output differs", file=sys.stderr)
                for difference in result.differences:
                    print(difference, file=sys.stderr)
        if failed:
            raise SystemExit(1)

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
        for template in names:
            print(f"{template}: running mise run check")
            template_root = repository.templates_root / template
            with tempfile.TemporaryDirectory(
                prefix=f"template-check-{template}-"
            ) as temporary:
                git_dir = Path(temporary) / "repo.git"
                index = Path(temporary) / "index"
                subprocess.run(
                    ["git", "init", "--bare", "--quiet", str(git_dir)], check=True
                )
                subprocess.run(
                    [
                        "git",
                        "--git-dir",
                        str(git_dir),
                        "config",
                        "core.bare",
                        "false",
                    ],
                    check=True,
                )
                subprocess.run(
                    [
                        "git",
                        "--git-dir",
                        str(git_dir),
                        "config",
                        "core.worktree",
                        str(template_root),
                    ],
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
                    raise TemplateError(
                        f"generated template unexpectedly contains .git: {template_root}"
                    )
                git_marker.write_text(f"gitdir: {git_dir}\n", encoding="utf-8")
                try:
                    check_environment = environment | {
                        "MISE_TRUSTED_CONFIG_PATHS": str(template_root)
                    }
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
                failed = True
                print(
                    f"{template}: mise run check exited with {completed.returncode}",
                    file=sys.stderr,
                )

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
    args = parser.parse_args(argv)

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
