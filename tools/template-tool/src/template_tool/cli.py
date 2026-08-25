from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import questionary

from .application import (
    DEFAULT_REPOSITORY,
    ApplicationError,
    apply_selected_template,
    ApplyResult,
    export_selected_template,
    ExportResult,
    initialize_selected_project,
    prepare_template,
    required_metadata,
    SelectedTemplate,
    select_template,
    selected_template_from_source,
    validate_apply_target,
    validate_export_destination,
)
from .instantiation import InstantiationError, validate_metadata_value
from .repository import TemplateError, TemplateRepository

_UVX_FROM = (
    'uvx --from "git+https://github.com/YewFence/template.git@main'
    '#subdirectory=tools/template-tool"'
)

_INIT_DESCRIPTION = """\
Initialize a new project from a template at the selected ref of the template
monorepo. The target must be a clean Git repository without any commits, and
the target path must be the repository root.

The tool validates the template contract, renders, and instantiates the
template in an isolated tree, creates the initial commit with your normal Git
identity (signing and hooks included), then stages the instantiated project as
uncommitted changes. It never guesses metadata, creates remotes, or commits
the template content for you."""

_INIT_EPILOG = f"""\
examples:
  {_UVX_FROM} init-project --ref main --template common --interactive .

Use --interactive to pick capabilities and answer metadata fields, or pass
--enable-capability/--disable-capability and metadata options for scripted
use. After instantiation, generate and commit the project's own dependency
lock state and GitHub Action digests as described in the README."""

_APPLY_DESCRIPTION = """\
Apply a template at the selected ref to an existing repository. The target
must be a clean Git repository with at least one commit, and must not be in
the middle of a merge, rebase, cherry-pick, or revert.

Template changes are staged to the Git index only; nothing is committed
automatically. Root .gitignore, AGENTS*, license, and notice files are
protected and skipped. Conflicting paths keep their Git index stages and
worktree state for manual resolution."""

_APPLY_EPILOG = f"""\
examples:
  {_UVX_FROM} apply-template --ref main --template go-cli --interactive .

Review the staged changes with `git status` and `git diff --cached`, then
commit them yourself. Cancel the whole application with `git reset --hard
HEAD`. Detached HEAD and colocated Jujutsu repositories are supported, but
finish, resolve, or cancel this Git application before continuing normal jj
operations."""

_EXPORT_DESCRIPTION = """\
Export a template at the selected ref as a standalone candidate tree for
manual comparison and selective copying, for example to diff a newer template
ref against an existing project.

The destination must not exist or be empty. Metadata is preset to placeholder
values so non-interactive exports need no project identity. The export creates
no .git directory, applies no protected-path filtering, and never touches an
existing project."""

_EXPORT_EPILOG = f"""\
examples:
  {_UVX_FROM} export-template --ref main --template rust --interactive ./rust-template-main

The exported tree is an unbootstrapped template blueprint: dependency lock
state and GitHub Action digests are not generated."""

_CAPABILITIES_DESCRIPTION = """\
Print the capabilities a template declares at the selected ref, together with
their default state. Read-only: the command only reads the capability contract
of the selected ref. It requires no Git repository and changes nothing."""

_CAPABILITIES_EPILOG = f"""\
examples:
  {_UVX_FROM} list-template-capabilities --ref main --template rust
  {_UVX_FROM} list-template-capabilities --ref main --template rust --json"""

_RENDER_DESCRIPTION = """\
Render template previews from the shared/ and overlays/ sources into
templates/<name>/ in the local monorepo checkout. Maintenance command; users
of the templates do not need it."""

_CHECK_DESCRIPTION = """\
Check that the committed template previews are in sync with their sources,
then validate every capability combination of each selected template in
disposable staging. Maintenance command; normally run by monorepo CI."""

_UMBRELLA_DESCRIPTION = """\
Unified entry point for all template tool commands. The user-facing commands
are also available as standalone entry points (init-project, apply-template,
export-template, list-template-capabilities) that bootstrap into the selected
ref's own locked tool version before running."""

_INTERACTIVE_HELP = (
    "choose capabilities and answer metadata fields interactively, "
    "with a summary confirmation before anything is changed"
)

_KEEP_TOKENS_HELP = (
    "stage the raw template blueprint without replacing {{METADATA}} tokens; "
    "cannot be combined with metadata options"
)


def _root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="monorepo root containing templates.toml (default: current directory)",
    )


def _selection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPOSITORY,
        help="template monorepo to fetch from (default: %(default)s)",
    )
    parser.add_argument(
        "--ref",
        required=True,
        help="Git ref of the template monorepo to select, e.g. main or a release tag; "
        "the template contract and renderer always come from this ref",
    )
    parser.add_argument(
        "--template",
        required=True,
        help="template profile declared in templates.toml (e.g. common, go-cli, rust)",
    )
    parser.add_argument("--source-checkout", type=Path, help=argparse.SUPPRESS)


def _metadata_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-name", help="project display name (metadata field: project_name)")
    parser.add_argument("--description", help="one-line project description (metadata field: description)")
    parser.add_argument("--github-owner", help="GitHub user or organization that will own the repository (metadata field: github_owner)")
    parser.add_argument("--repo-name", help="GitHub repository name (metadata field: repo_name)")
    parser.add_argument("--go-module", help="Go module path; go-cli template only (metadata field: go_module)")
    parser.add_argument("--cargo-package", help="Cargo package name; rust template only (metadata field: cargo_package)")
    parser.add_argument("--binary-name", help="name of the compiled binary; go-cli and rust templates only (metadata field: binary_name)")


def _capability_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--enable-capability",
        action="append",
        default=[],
        help="enable a template capability, overriding the profile default; repeatable",
    )
    parser.add_argument(
        "--disable-capability",
        action="append",
        default=[],
        help="disable a template capability, overriding the profile default; repeatable",
    )


def _render_parent() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("template", nargs="?", help="template name; defaults to all")
    parser.add_argument("--check", action="store_true", help="compare generated output without writing")
    _root_argument(parser)
    return parser


def _check_parent() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("template", nargs="?", help="template name; defaults to all")
    _root_argument(parser)
    return parser


def _apply_parent() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="existing clean Git repository to receive the template (default: current directory)",
    )
    _selection_arguments(parser)
    _metadata_arguments(parser)
    _capability_arguments(parser)
    parser.add_argument("--interactive", action="store_true", help=_INTERACTIVE_HELP)
    parser.add_argument("--keep-tokens", action="store_true", help=_KEEP_TOKENS_HELP)
    return parser


def _init_parent() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="clean Git repository without commits to initialize; must be the repository root (default: current directory)",
    )
    _selection_arguments(parser)
    _metadata_arguments(parser)
    _capability_arguments(parser)
    parser.add_argument("--interactive", action="store_true", help=_INTERACTIVE_HELP)
    parser.add_argument("--keep-tokens", action="store_true", help=_KEEP_TOKENS_HELP)
    return parser


def _export_parent() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "destination",
        type=Path,
        help="directory for the candidate tree; must not exist or be empty",
    )
    _selection_arguments(parser)
    _metadata_arguments(parser)
    _capability_arguments(parser)
    parser.add_argument("--interactive", action="store_true", help=_INTERACTIVE_HELP)
    return parser


def _capabilities_parent() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    _selection_arguments(parser)
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the capability contract as a stable single-line JSON object for scripting",
    )
    return parser


def _render_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="render-template",
        parents=[_render_parent()],
        description=_RENDER_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def _check_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="check-templates",
        parents=[_check_parent()],
        description=_CHECK_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def _apply_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="apply-template",
        parents=[_apply_parent()],
        description=_APPLY_DESCRIPTION,
        epilog=_APPLY_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def _init_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="init-project",
        parents=[_init_parent()],
        description=_INIT_DESCRIPTION,
        epilog=_INIT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def _export_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="export-template",
        parents=[_export_parent()],
        description=_EXPORT_DESCRIPTION,
        epilog=_EXPORT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def _capabilities_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="list-template-capabilities",
        parents=[_capabilities_parent()],
        description=_CAPABILITIES_DESCRIPTION,
        epilog=_CAPABILITIES_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def user_parsers() -> tuple[argparse.ArgumentParser, ...]:
    """Parsers of the user-facing standalone entry points, in documentation order."""
    return (_init_parser(), _apply_parser(), _export_parser(), _capabilities_parser())


def maintenance_parsers() -> tuple[argparse.ArgumentParser, ...]:
    """Parsers of the monorepo maintenance entry points, in documentation order."""
    return (_render_parser(), _check_parser())


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

        failures: list[tuple[str, str]] = []
        for template in names:
            for case, enabled_capabilities in _validation_cases(repository, template):
                print(f"{case}: running disposable staging validation")
                try:
                    _run_template_project_check(
                        repository, template, enabled_capabilities
                    )
                except TemplateError as error:
                    failures.append((case, str(error)))
                except subprocess.CalledProcessError as error:
                    failures.append(
                        (
                            case,
                            f"command failed with exit code {error.returncode}: "
                            f"{error.cmd}",
                        )
                    )
        if failures:
            print("staging validation failures:", file=sys.stderr)
            for case, reason in failures:
                print(f"{case}: {reason}", file=sys.stderr)
            raise SystemExit(1)
    except TemplateError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
    except subprocess.CalledProcessError as error:
        print(f"command failed with exit code {error.returncode}: {error.cmd}", file=sys.stderr)
        raise SystemExit(1) from error


def _validation_cases(
    repository: TemplateRepository, template: str
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    capabilities = tuple(name for name, _ in repository.capabilities(template))
    cases = []
    for selection in itertools.product((False, True), repeat=len(capabilities)):
        enabled = tuple(
            capability
            for capability, selected in zip(capabilities, selection, strict=True)
            if selected
        )
        states = ",".join(
            f"{capability}={'on' if selected else 'off'}"
            for capability, selected in zip(capabilities, selection, strict=True)
        )
        cases.append((f"{template}[{states or 'no-capabilities'}]", enabled))
    return tuple(cases)


def _run_template_project_check(
    repository: TemplateRepository,
    template: str,
    enabled_capabilities: tuple[str, ...],
) -> None:
    enabled_capabilities = tuple(sorted(enabled_capabilities))
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
        try:
            prepare_template(
                repository,
                template,
                template_root,
                metadata=repository.validation_metadata(template),
                enabled_capabilities=enabled_capabilities,
            )
        except ApplicationError as error:
            raise TemplateError(str(error)) from error

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
            "MISE_TRUSTED_CONFIG_PATHS": f"{repository.root}:{overlay_root}:{template_root}",
            "TEMPLATE_TOOL_ENABLED_CAPABILITIES": json.dumps(
                enabled_capabilities, separators=(",", ":")
            ),
        }
        completed = subprocess.run(
            ["mise", "run", f"//overlays/{template}:check", str(template_root)],
            cwd=repository.root,
            env=check_environment,
            check=False,
        )
    if completed.returncode != 0:
        raise TemplateError(f"overlay check exited with {completed.returncode}")


def apply_main(argv: list[str] | None = None) -> None:
    args = _apply_parser().parse_args(argv)
    metadata = _metadata_from_args(args)
    try:
        if args.keep_tokens and metadata:
            raise ApplicationError("--keep-tokens cannot be combined with metadata")
        validate_apply_target(args.target)
        selected = (
            selected_template_from_source(args.repo, args.ref, args.source_checkout)
            if args.source_checkout is not None
            else None
        )
        if selected is not None:
            capabilities = _resolve_interactive_selection(
                selected,
                args.template,
                enable=tuple(args.enable_capability),
                disable=tuple(args.disable_capability),
                interactive=args.interactive,
            )
            if args.interactive and not args.keep_tokens:
                metadata = _collect_metadata_for_fields(
                    selected.required_metadata(args.template), metadata, confirm=False
                )
            if args.interactive:
                _confirm_selection(args.template, capabilities, metadata)
            result = apply_selected_template(
                selected,
                args.template,
                args.target,
                metadata=None if args.keep_tokens else metadata,
                enabled_capabilities=capabilities,
                keep_tokens=args.keep_tokens,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="apply-template-") as temporary:
                with select_template(args.repo, args.ref, Path(temporary)) as selected:
                    capabilities = _resolve_interactive_selection(
                        selected,
                        args.template,
                        enable=tuple(args.enable_capability),
                        disable=tuple(args.disable_capability),
                        interactive=args.interactive,
                    )
                    if args.interactive and not args.keep_tokens:
                        metadata = _collect_metadata_for_fields(
                            selected.required_metadata(args.template),
                            metadata,
                            confirm=False,
                        )
                    if args.interactive:
                        _confirm_selection(args.template, capabilities, metadata)
                    result = apply_selected_template(
                        selected,
                        args.template,
                        args.target,
                        metadata=None if args.keep_tokens else metadata,
                        enabled_capabilities=capabilities,
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


def _edit_metadata_for_fields(
    required: tuple[str, ...], current: dict[str, str]
) -> dict[str, str]:
    metadata = dict(current)
    try:
        for field in required:
            while True:
                value = questionary.text(
                    field.replace("_", " ").title(), default=metadata[field]
                ).ask()
                if value is None:
                    raise ApplicationError("interactive metadata editing cancelled")
                try:
                    validate_metadata_value(field, value)
                except InstantiationError as error:
                    print(f"error: {error}", file=sys.stderr)
                    continue
                metadata[field] = value
                break
    except (KeyboardInterrupt, EOFError):
        raise ApplicationError("interactive metadata editing cancelled") from None
    return metadata


def _collect_metadata(
    repository: str,
    reference: str,
    template: str,
    provided: dict[str, str],
) -> dict[str, str]:
    required = required_metadata(repository, reference, template)
    return _collect_metadata_for_fields(required, provided)


def _collect_metadata_for_fields(
    required: tuple[str, ...],
    provided: dict[str, str],
    *,
    confirm: bool = True,
) -> dict[str, str]:
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
        if confirm:
            summary = "\n".join(f"{field}: {metadata[field]}" for field in required)
            confirmed = questionary.confirm(
                f"Confirm metadata?\n{summary}", default=True
            ).ask()
            if confirmed is not True:
                raise ApplicationError("interactive metadata collection cancelled")
    except (KeyboardInterrupt, EOFError):
        raise ApplicationError("interactive metadata collection cancelled") from None
    return metadata


def _resolve_interactive_selection(
    selected: SelectedTemplate,
    template: str,
    *,
    enable: tuple[str, ...],
    disable: tuple[str, ...],
    interactive: bool,
) -> tuple[str, ...]:
    explicit = set(enable) | set(disable)
    enabled = list(enable)
    disabled = list(disable)
    try:
        selected.resolve_capabilities(template, enable=enable, disable=disable)
        if interactive:
            for name, default_enabled in selected.capabilities(template):
                if name in explicit:
                    continue
                answer = questionary.confirm(
                    f"Enable capability {name}?", default=default_enabled
                ).ask()
                if answer is None:
                    raise ApplicationError("interactive capability selection cancelled")
                (enabled if answer else disabled).append(name)
    except (KeyboardInterrupt, EOFError):
        raise ApplicationError("interactive capability selection cancelled") from None
    return selected.resolve_capabilities(
        template, enable=tuple(enabled), disable=tuple(disabled)
    )


def _confirm_selection(
    template: str, capabilities: tuple[str, ...], metadata: dict[str, str]
) -> None:
    capability_summary = ", ".join(capabilities) or "(none)"
    lines = [f"Template: {template}", f"Capabilities: {capability_summary}"]
    lines.extend(f"{field}: {value}" for field, value in metadata.items())
    try:
        confirmed = questionary.confirm(
            "Confirm selection?\n" + "\n".join(lines), default=True
        ).ask()
    except (KeyboardInterrupt, EOFError):
        raise ApplicationError("interactive selection cancelled") from None
    if confirmed is not True:
        raise ApplicationError("interactive selection cancelled")


def init_main(argv: list[str] | None = None) -> None:
    args = _init_parser().parse_args(argv)
    metadata = _metadata_from_args(args)
    try:
        if args.keep_tokens and metadata:
            raise ApplicationError("--keep-tokens cannot be combined with metadata")
        selected = (
            selected_template_from_source(args.repo, args.ref, args.source_checkout)
            if args.source_checkout is not None
            else None
        )
        if selected is not None:
            capabilities = _resolve_interactive_selection(
                selected,
                args.template,
                enable=tuple(args.enable_capability),
                disable=tuple(args.disable_capability),
                interactive=args.interactive,
            )
            if args.interactive and not args.keep_tokens:
                metadata = _collect_metadata_for_fields(
                    selected.required_metadata(args.template), metadata, confirm=False
                )
            if args.interactive:
                _confirm_selection(args.template, capabilities, metadata)
            result = initialize_selected_project(
                selected,
                args.template,
                args.target,
                None if args.keep_tokens else metadata,
                enabled_capabilities=capabilities,
                keep_tokens=args.keep_tokens,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="init-project-") as temporary:
                with select_template(args.repo, args.ref, Path(temporary)) as selected:
                    capabilities = _resolve_interactive_selection(
                        selected,
                        args.template,
                        enable=tuple(args.enable_capability),
                        disable=tuple(args.disable_capability),
                        interactive=args.interactive,
                    )
                    if args.interactive and not args.keep_tokens:
                        metadata = _collect_metadata_for_fields(
                            selected.required_metadata(args.template),
                            metadata,
                            confirm=False,
                        )
                    if args.interactive:
                        _confirm_selection(args.template, capabilities, metadata)
                    result = initialize_selected_project(
                        selected,
                        args.template,
                        args.target,
                        None if args.keep_tokens else metadata,
                        enabled_capabilities=capabilities,
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
    print(f"Initial-Commit: {result.initial_commit}")
    _print_apply_result(result.application)
    if result.application.conflicted:
        raise SystemExit(1)


def export_main(argv: list[str] | None = None) -> None:
    args = _export_parser().parse_args(argv)
    overrides = _metadata_from_args(args)
    try:
        validate_export_destination(args.destination)
        selected = (
            selected_template_from_source(args.repo, args.ref, args.source_checkout)
            if args.source_checkout is not None
            else None
        )
        if selected is not None:
            result = _export_with_selected(selected, args, overrides)
        else:
            with tempfile.TemporaryDirectory(prefix="export-template-") as temporary:
                with select_template(args.repo, args.ref, Path(temporary)) as selected:
                    result = _export_with_selected(selected, args, overrides)
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
    _print_export_result(result)


def _export_with_selected(
    selected: SelectedTemplate,
    args: argparse.Namespace,
    overrides: dict[str, str],
) -> ExportResult:
    metadata = selected.export_metadata(args.template) | overrides
    capabilities = _resolve_interactive_selection(
        selected,
        args.template,
        enable=tuple(args.enable_capability),
        disable=tuple(args.disable_capability),
        interactive=args.interactive,
    )
    if args.interactive:
        metadata = _edit_metadata_for_fields(
            selected.required_metadata(args.template), metadata
        )
        _confirm_export_selection(
            selected,
            args.template,
            capabilities,
            metadata,
            args.destination.resolve(),
        )
    return export_selected_template(
        selected,
        args.template,
        args.destination,
        metadata,
        enabled_capabilities=capabilities,
    )


def _confirm_export_selection(
    selected: SelectedTemplate,
    template: str,
    capabilities: tuple[str, ...],
    metadata: dict[str, str],
    destination: Path,
) -> None:
    lines = [
        f"Repository: {selected.repository}",
        f"Ref: {selected.reference}",
        f"Template-Commit: {selected.commit}",
        f"Template: {template}",
        f"Capabilities: {', '.join(capabilities) or '(none)'}",
    ]
    lines.extend(f"{field}: {value}" for field, value in metadata.items())
    lines.append(f"Destination: {destination}")
    try:
        confirmed = questionary.confirm(
            "Confirm export?\n" + "\n".join(lines), default=True
        ).ask()
    except (KeyboardInterrupt, EOFError):
        raise ApplicationError("interactive export cancelled") from None
    if confirmed is not True:
        raise ApplicationError("interactive export cancelled")


def _print_export_result(result: ExportResult) -> None:
    print(f"Repository: {result.repository}")
    print(f"Template: {result.template}")
    print(f"Ref: {result.reference}")
    print(f"Template-Commit: {result.commit}")
    print(f"Capabilities: {', '.join(result.capabilities) or '(none)'}")
    print(f"Destination: {result.destination}")
    print(
        "HINT: this candidate tree is only for manual comparison and selective copying; no existing project was updated."
    )
    print(
        "HINT: the exported tree is unbootstrapped and does not include generated dependency or GitHub Action lock state."
    )


def _print_apply_result(result: ApplyResult) -> None:
    print(f"Repository: {result.repository}")
    print(f"Template: {result.template}")
    print(f"Ref: {result.reference}")
    print(f"Template-Commit: {result.commit}")
    print(f"Capabilities: {', '.join(result.capabilities) or '(none)'}")
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


def capabilities_main(argv: list[str] | None = None) -> None:
    args = _capabilities_parser().parse_args(argv)
    try:
        selected = (
            selected_template_from_source(args.repo, args.ref, args.source_checkout)
            if args.source_checkout is not None
            else None
        )
        if selected is not None:
            _print_capabilities(selected, args.template, as_json=args.json)
        else:
            with tempfile.TemporaryDirectory(prefix="template-capabilities-") as temporary:
                with select_template(args.repo, args.ref, Path(temporary)) as selected:
                    _print_capabilities(selected, args.template, as_json=args.json)
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


def _print_capabilities(
    selected: SelectedTemplate, template: str, *, as_json: bool
) -> None:
    capabilities = selected.capabilities(template)
    if as_json:
        print(
            json.dumps(
                {
                    "repository": selected.repository,
                    "ref": selected.reference,
                    "commit": selected.commit,
                    "template": template,
                    "capabilities": [
                        {"name": name, "default_enabled": default_enabled}
                        for name, default_enabled in capabilities
                    ],
                },
                separators=(",", ":"),
            )
        )
        return
    print(f"Repository: {selected.repository}")
    print(f"Template: {template}")
    print(f"Ref: {selected.reference}")
    print(f"Template-Commit: {selected.commit}")
    for name, default_enabled in capabilities:
        state = "enabled" if default_enabled else "disabled"
        print(f"Capability: {name} (default: {state})")


def umbrella_parser() -> argparse.ArgumentParser:
    """The unified `template-tool` parser with every command as a subcommand."""
    parser = argparse.ArgumentParser(
        prog="template-tool",
        description=_UMBRELLA_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "render",
        parents=[_render_parent()],
        help="render template previews from sources",
        description=_RENDER_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers.add_parser(
        "check",
        parents=[_check_parent()],
        help="validate templates in disposable staging",
        description=_CHECK_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers.add_parser(
        "apply",
        parents=[_apply_parent()],
        help="apply a template to an existing repository",
        description=_APPLY_DESCRIPTION,
        epilog=_APPLY_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers.add_parser(
        "init",
        parents=[_init_parent()],
        help="initialize a new project from a template",
        description=_INIT_DESCRIPTION,
        epilog=_INIT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers.add_parser(
        "export",
        parents=[_export_parent()],
        help="export a standalone candidate tree",
        description=_EXPORT_DESCRIPTION,
        epilog=_EXPORT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers.add_parser(
        "capabilities",
        parents=[_capabilities_parent()],
        help="list a template's declared capabilities",
        description=_CAPABILITIES_DESCRIPTION,
        epilog=_CAPABILITIES_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = umbrella_parser().parse_args(argv)
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
        for capability in args.enable_capability:
            forwarded.extend(["--enable-capability", capability])
        for capability in args.disable_capability:
            forwarded.extend(["--disable-capability", capability])
        if args.source_checkout is not None:
            forwarded.extend(["--source-checkout", str(args.source_checkout)])
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
        if args.keep_tokens:
            forwarded.append("--keep-tokens")
        for capability in args.enable_capability:
            forwarded.extend(["--enable-capability", capability])
        for capability in args.disable_capability:
            forwarded.extend(["--disable-capability", capability])
        if args.source_checkout is not None:
            forwarded.extend(["--source-checkout", str(args.source_checkout)])
        init_main(forwarded)
        return
    if args.command == "capabilities":
        forwarded = [
            "--repo",
            args.repo,
            "--ref",
            args.ref,
            "--template",
            args.template,
        ]
        if args.json:
            forwarded.append("--json")
        if args.source_checkout is not None:
            forwarded.extend(["--source-checkout", str(args.source_checkout)])
            capabilities_main(forwarded)
        else:
            from .bootstrap import capabilities_main as run_selected_capabilities

            run_selected_capabilities(forwarded)
        return
    if args.command == "export":
        forwarded = [
            str(args.destination),
            "--repo",
            args.repo,
            "--ref",
            args.ref,
            "--template",
            args.template,
        ]
        for option in ("project-name", "description", "github-owner", "repo-name", "go-module", "cargo-package", "binary-name"):
            value = getattr(args, option.replace("-", "_"))
            if value is not None:
                forwarded.extend([f"--{option}", value])
        if args.interactive:
            forwarded.append("--interactive")
        for capability in args.enable_capability:
            forwarded.extend(["--enable-capability", capability])
        for capability in args.disable_capability:
            forwarded.extend(["--disable-capability", capability])
        if args.source_checkout is not None:
            forwarded.extend(["--source-checkout", str(args.source_checkout)])
            export_main(forwarded)
        else:
            from .bootstrap import export_main as run_selected_export

            run_selected_export(forwarded)
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
