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
            "MISE_TRUSTED_CONFIG_PATHS": f"{overlay_root}:{template_root}",
            "TEMPLATE_TOOL_ENABLED_CAPABILITIES": json.dumps(
                enabled_capabilities, separators=(",", ":")
            ),
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
    parser.add_argument("--source-checkout", type=Path, help=argparse.SUPPRESS)
    _metadata_arguments(parser)
    _capability_arguments(parser)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--keep-tokens", action="store_true")
    return parser


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


def _init_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="init-project")
    parser.add_argument("target", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--ref", required=True, help="Git ref to fetch")
    parser.add_argument("--template", required=True, help="template name")
    parser.add_argument("--source-checkout", type=Path, help=argparse.SUPPRESS)
    _metadata_arguments(parser)
    _capability_arguments(parser)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--keep-tokens", action="store_true")
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


def _capability_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--enable-capability", action="append", default=[])
    parser.add_argument("--disable-capability", action="append", default=[])


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


def _export_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="export-template")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--ref", required=True, help="Git ref to fetch")
    parser.add_argument("--template", required=True, help="template name")
    parser.add_argument("--source-checkout", type=Path, help=argparse.SUPPRESS)
    _metadata_arguments(parser)
    _capability_arguments(parser)
    parser.add_argument("--interactive", action="store_true")
    return parser


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


def _capabilities_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="list-template-capabilities")
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--ref", required=True, help="Git ref to fetch")
    parser.add_argument("--template", required=True, help="template name")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--source-checkout", type=Path, help=argparse.SUPPRESS)
    return parser


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
    apply_parser.add_argument("--source-checkout", type=Path, help=argparse.SUPPRESS)
    _metadata_arguments(apply_parser)
    _capability_arguments(apply_parser)
    apply_parser.add_argument("--interactive", action="store_true")
    apply_parser.add_argument("--keep-tokens", action="store_true")
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("target", nargs="?", type=Path, default=Path.cwd())
    init_parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    init_parser.add_argument("--ref", required=True)
    init_parser.add_argument("--template", required=True)
    init_parser.add_argument("--source-checkout", type=Path, help=argparse.SUPPRESS)
    _metadata_arguments(init_parser)
    _capability_arguments(init_parser)
    init_parser.add_argument("--interactive", action="store_true")
    init_parser.add_argument("--keep-tokens", action="store_true")
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("destination", type=Path)
    export_parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    export_parser.add_argument("--ref", required=True)
    export_parser.add_argument("--template", required=True)
    export_parser.add_argument("--source-checkout", type=Path, help=argparse.SUPPRESS)
    _metadata_arguments(export_parser)
    _capability_arguments(export_parser)
    export_parser.add_argument("--interactive", action="store_true")
    capabilities_parser = subparsers.add_parser("capabilities")
    capabilities_parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    capabilities_parser.add_argument("--ref", required=True)
    capabilities_parser.add_argument("--template", required=True)
    capabilities_parser.add_argument("--json", action="store_true")
    capabilities_parser.add_argument(
        "--source-checkout", type=Path, help=argparse.SUPPRESS
    )
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
