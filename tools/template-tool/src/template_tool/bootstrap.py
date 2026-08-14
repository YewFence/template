from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from .application import DEFAULT_REPOSITORY
from .cli import apply_main as run_apply
from .cli import capabilities_main as run_capabilities
from .cli import export_main as run_export
from .cli import init_main as run_init


def apply_main(argv: list[str] | None = None) -> None:
    _run_selected_engine("apply", list(sys.argv[1:] if argv is None else argv), run_apply)


def init_main(argv: list[str] | None = None) -> None:
    _run_selected_engine("init", list(sys.argv[1:] if argv is None else argv), run_init)


def capabilities_main(argv: list[str] | None = None) -> None:
    _run_selected_engine(
        "capabilities",
        list(sys.argv[1:] if argv is None else argv),
        run_capabilities,
    )


def export_main(argv: list[str] | None = None) -> None:
    _run_selected_engine(
        "export",
        list(sys.argv[1:] if argv is None else argv),
        run_export,
    )


def _run_selected_engine(
    command: str,
    arguments: list[str],
    local_main: Callable[[list[str]], None],
) -> None:
    if any(argument in {"-h", "--help"} for argument in arguments):
        local_main(arguments)
        return
    repository, reference = _selection_arguments(arguments)
    with tempfile.TemporaryDirectory(prefix="template-tool-bootstrap-") as temporary:
        source = Path(temporary) / "source"
        subprocess.run(["git", "init", "--quiet", str(source)], check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", repository], cwd=source, check=True
        )
        subprocess.run(
            [
                "git",
                "fetch",
                "--quiet",
                "--no-tags",
                "--depth=1",
                "--filter=blob:none",
                "origin",
                reference,
            ],
            cwd=source,
            check=True,
        )
        commit = subprocess.run(
            ["git", "rev-parse", "FETCH_HEAD^{commit}"],
            cwd=source,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "checkout", "--quiet", "--detach", commit],
            cwd=source,
            check=True,
        )
        completed = subprocess.run(
            [
                "uv",
                "run",
                "--locked",
                "--project",
                str(source / "tools/template-tool"),
                "python",
                "-m",
                "template_tool",
                command,
                "--source-checkout",
                str(source),
                *arguments,
            ],
            check=False,
        )
    if completed.returncode:
        raise SystemExit(completed.returncode)


def _selection_arguments(arguments: list[str]) -> tuple[str, str]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--ref", required=True)
    args, _ = parser.parse_known_args(arguments)
    return args.repo, args.ref
