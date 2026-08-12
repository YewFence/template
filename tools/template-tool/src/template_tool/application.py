from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .instantiation import InstantiationError, build_token_values
from .repository import TemplateError, TemplateRepository
from .configuration import ConfigurationError, load_template_config


class ApplicationError(RuntimeError):
    """Raised when a template cannot be safely applied."""


DEFAULT_REPOSITORY = "https://github.com/YewFence/template.git"


@dataclass(frozen=True)
class ApplyPolicy:
    protected: tuple[str, ...]
    hints: tuple[str, ...]


@dataclass(frozen=True)
class ApplyResult:
    repository: str
    template: str
    reference: str
    commit: str
    capabilities: tuple[str, ...]
    skipped: tuple[str, ...]
    hints: tuple[str, ...]
    conflicted: bool
    jujutsu: bool
    instantiated: bool


@dataclass(frozen=True)
class InitProjectResult:
    initial_commit: str
    application: ApplyResult


@dataclass(frozen=True)
class SelectedTemplate:
    repository: str
    reference: str
    commit: str
    source: Path
    policy: ApplyPolicy
    templates: TemplateRepository

    def required_metadata(self, template: str) -> tuple[str, ...]:
        try:
            self.templates.select(template)
            return self.templates.required_metadata(template)
        except TemplateError as error:
            raise ApplicationError(str(error)) from error

    def capabilities(self, template: str) -> tuple[tuple[str, bool], ...]:
        try:
            self.templates.select(template)
            return self.templates.capabilities(template)
        except TemplateError as error:
            raise ApplicationError(str(error)) from error

    def resolve_capabilities(
        self,
        template: str,
        *,
        enable: tuple[str, ...] = (),
        disable: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        try:
            self.templates.select(template)
            return self.templates.resolve_capabilities(
                template, enable=enable, disable=disable
            )
        except TemplateError as error:
            raise ApplicationError(str(error)) from error

    def prepare(
        self,
        template: str,
        destination: Path | str,
        *,
        metadata: dict[str, str] | None = None,
        enabled_capabilities: tuple[str, ...] | None = None,
    ) -> Path:
        return prepare_template(
            self.templates,
            template,
            destination,
            metadata=metadata,
            enabled_capabilities=enabled_capabilities,
        )


def prepare_template(
    templates: TemplateRepository,
    template: str,
    destination: Path | str,
    *,
    metadata: dict[str, str] | None = None,
    enabled_capabilities: tuple[str, ...] | None = None,
) -> Path:
    templates.select(template)
    prepared = Path(destination).resolve()
    try:
        if metadata is not None:
            build_token_values(metadata, templates.instantiation_spec(template))
        templates.render_to(
            template,
            prepared,
            enabled_capabilities=enabled_capabilities,
        )
        if metadata is not None:
            templates.instantiate(template, prepared, metadata)
    except (TemplateError, InstantiationError) as error:
        raise ApplicationError(f"cannot prepare {template!r}: {error}") from error
    return prepared


def initialize_project(
    repository: str,
    reference: str,
    template: str,
    target: Path | str,
    metadata: dict[str, str] | None,
    *,
    enabled_capabilities: tuple[str, ...] | None = None,
    keep_tokens: bool = False,
) -> InitProjectResult:
    _validate_template_name(template)
    target_root = _unborn_target_root(Path(target))
    _require_clean_repository(target_root)
    _require_idle_repository(target_root)
    with tempfile.TemporaryDirectory(prefix="init-project-") as temporary:
        temporary_root = Path(temporary)
        with select_template(repository, reference, temporary_root) as selected:
            return initialize_selected_project(
                selected,
                template,
                target_root,
                metadata,
                enabled_capabilities=enabled_capabilities,
                keep_tokens=keep_tokens,
            )


def initialize_selected_project(
    selected: SelectedTemplate,
    template: str,
    target: Path | str,
    metadata: dict[str, str] | None,
    *,
    enabled_capabilities: tuple[str, ...] | None = None,
    keep_tokens: bool = False,
) -> InitProjectResult:
    _validate_template_name(template)
    if keep_tokens and metadata is not None:
        raise ApplicationError("--keep-tokens cannot be combined with metadata")
    target_root = _unborn_target_root(Path(target))
    _require_clean_repository(target_root)
    _require_idle_repository(target_root)
    with tempfile.TemporaryDirectory(prefix="init-project-prepared-") as temporary:
        temporary_root = Path(temporary)
        effective_capabilities = _effective_capabilities(
            selected, template, enabled_capabilities
        )
        prepared = selected.prepare(
            template,
            temporary_root / "prepared",
            metadata=None if keep_tokens else metadata,
            enabled_capabilities=effective_capabilities,
        )
        temporary_commit, skipped, commit_source = _prepared_template_commit(
            prepared,
            template,
            (),
            temporary_root,
        )
        _unborn_target_root(target_root)
        _require_clean_repository(target_root)
        _require_idle_repository(target_root)
        try:
            _run(
                [
                    "git",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "chore: initialize repository",
                ],
                cwd=target_root,
            )
        except subprocess.CalledProcessError as error:
            raise ApplicationError(
                "cannot create the initial commit; review the Git author identity, signing, and hooks"
            ) from error
        initial_commit = _output(["git", "rev-parse", "HEAD^{commit}"], cwd=target_root)
        application = _apply_prepared_template(
            selected,
            template,
            target_root,
            temporary_commit,
            commit_source,
            skipped,
            protect=False,
            instantiated=not keep_tokens,
            capabilities=effective_capabilities,
        )
    return InitProjectResult(initial_commit, application)


def apply_selected_template(
    selected: SelectedTemplate,
    template: str,
    target: Path | str,
    metadata: dict[str, str] | None = None,
    *,
    enabled_capabilities: tuple[str, ...] | None = None,
    keep_tokens: bool = False,
) -> ApplyResult:
    _validate_template_name(template)
    if keep_tokens and metadata is not None:
        raise ApplicationError("--keep-tokens cannot be combined with metadata")
    target_root = _validated_apply_target_root(Path(target))
    with tempfile.TemporaryDirectory(prefix="apply-template-prepared-") as temporary:
        temporary_root = Path(temporary)
        effective_capabilities = _effective_capabilities(
            selected, template, enabled_capabilities
        )
        prepared = selected.prepare(
            template,
            temporary_root / "prepared",
            metadata=None if keep_tokens else metadata,
            enabled_capabilities=effective_capabilities,
        )
        temporary_commit, skipped, commit_source = _prepared_template_commit(
            prepared,
            template,
            selected.policy.protected,
            temporary_root,
        )
        _require_clean_repository(target_root)
        _require_idle_repository(target_root)
        return _apply_prepared_template(
            selected,
            template,
            target_root,
            temporary_commit,
            commit_source,
            skipped,
            protect=True,
            instantiated=not keep_tokens,
            capabilities=effective_capabilities,
        )


def apply_template(
    repository: str,
    reference: str,
    template: str,
    target: Path | str,
    metadata: dict[str, str] | None = None,
    *,
    enabled_capabilities: tuple[str, ...] | None = None,
    keep_tokens: bool = False,
) -> ApplyResult:
    _validate_template_name(template)
    if keep_tokens and metadata is not None:
        raise ApplicationError("--keep-tokens cannot be combined with metadata")
    target_root = _validated_apply_target_root(Path(target))
    with tempfile.TemporaryDirectory(prefix="apply-template-") as temporary:
        with select_template(repository, reference, Path(temporary)) as selected:
            return apply_selected_template(
                selected,
                template,
                target_root,
                metadata=None if keep_tokens else metadata,
                enabled_capabilities=enabled_capabilities,
                keep_tokens=keep_tokens,
            )


def validate_apply_target(target: Path | str) -> None:
    """Validate that a target repository can safely accept template changes."""
    _validated_apply_target_root(Path(target))


def _effective_capabilities(
    selected: SelectedTemplate,
    template: str,
    enabled_capabilities: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if enabled_capabilities is None:
        return selected.resolve_capabilities(template)
    requested = set(enabled_capabilities)
    return selected.resolve_capabilities(
        template,
        enable=enabled_capabilities,
        disable=tuple(
            name for name, _ in selected.capabilities(template) if name not in requested
        ),
    )


def required_metadata(
    repository: str, reference: str, template: str
) -> tuple[str, ...]:
    _validate_template_name(template)
    with tempfile.TemporaryDirectory(prefix="template-contract-") as temporary:
        with select_template(repository, reference, Path(temporary)) as selected:
            return selected.required_metadata(template)


def _apply_prepared_template(
    selected: SelectedTemplate,
    template: str,
    target_root: Path,
    temporary_commit: str,
    commit_source: Path,
    skipped: tuple[str, ...],
    *,
    protect: bool,
    instantiated: bool,
    capabilities: tuple[str, ...],
) -> ApplyResult:
    _run(
        ["git", "fetch", "--quiet", "--no-tags", str(commit_source), temporary_commit],
        cwd=target_root,
    )
    completed = subprocess.run(
        [
            "git",
            "merge",
            "--squash",
            "--allow-unrelated-histories",
            "--no-edit",
            "FETCH_HEAD",
        ],
        cwd=target_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=os.sys.stderr)

    conflicted = bool(_output_bytes(["git", "ls-files", "-u"], cwd=target_root))
    merge_head = _git_path(target_root, "MERGE_HEAD")
    if merge_head.exists():
        _run(["git", "reset", "--hard", "HEAD"], cwd=target_root)
        raise ApplicationError("squash merge unexpectedly created MERGE_HEAD")
    if completed.returncode != 0 and not conflicted:
        _run(["git", "reset", "--hard", "HEAD"], cwd=target_root)
        raise ApplicationError(
            f"git squash merge failed with exit code {completed.returncode}"
        )
    return ApplyResult(
        repository=selected.repository,
        template=template,
        reference=selected.reference,
        commit=selected.commit,
        capabilities=capabilities,
        skipped=skipped,
        hints=selected.policy.hints if protect else (),
        conflicted=conflicted,
        jujutsu=(target_root / ".jj").exists(),
        instantiated=instantiated,
    )


@contextmanager
def select_template(
    repository: str, reference: str, temporary: Path
) -> Iterator[SelectedTemplate]:
    source = temporary / "source"
    _run(["git", "init", "--quiet", str(source)])
    _run(["git", "remote", "add", "origin", repository], cwd=source)
    _run(
        ["git", "fetch", "--quiet", "--no-tags", "--depth=1", "--filter=blob:none", "origin", reference],
        cwd=source,
    )
    commit = _output(["git", "rev-parse", "FETCH_HEAD^{commit}"], cwd=source)
    _run(["git", "checkout", "--quiet", "--detach", commit], cwd=source)
    policy, templates = _load_apply_config(source / "templates.toml")
    try:
        repository_reader = TemplateRepository(source)
    except TemplateError as error:
        raise ApplicationError(f"invalid fetched templates.toml: {error}") from error
    if tuple(repository_reader.template_names) != templates:
        raise ApplicationError("fetched templates.toml has inconsistent template declarations")
    yield SelectedTemplate(
        repository,
        reference,
        commit,
        source,
        policy,
        repository_reader,
    )


def selected_template_from_source(
    repository: str, reference: str, source: Path | str
) -> SelectedTemplate:
    source_root = Path(source).resolve()
    try:
        commit = _output(["git", "rev-parse", "HEAD^{commit}"], cwd=source_root)
    except subprocess.CalledProcessError as error:
        raise ApplicationError(f"selected source is not a Git checkout: {source_root}") from error
    policy, templates = _load_apply_config(source_root / "templates.toml")
    try:
        repository_reader = TemplateRepository(source_root)
    except TemplateError as error:
        raise ApplicationError(f"invalid selected templates.toml: {error}") from error
    if tuple(repository_reader.template_names) != templates:
        raise ApplicationError("selected templates.toml has inconsistent template declarations")
    return SelectedTemplate(
        repository,
        reference,
        commit,
        source_root,
        policy,
        repository_reader,
    )


def _validate_template_name(template: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", template):
        raise ApplicationError(f"invalid template name: {template!r}")


def _target_root(target: Path) -> Path:
    if not target.is_dir():
        raise ApplicationError(f"target directory does not exist: {target}")
    try:
        root = _output(["git", "rev-parse", "--show-toplevel"], cwd=target)
        _output(["git", "rev-parse", "--verify", "HEAD^{commit}"], cwd=target)
    except subprocess.CalledProcessError as error:
        raise ApplicationError(
            f"target must be an existing Git repository with at least one commit: {target}"
        ) from error
    return Path(root).resolve()


def _validated_apply_target_root(target: Path) -> Path:
    target_root = _target_root(target)
    _require_clean_repository(target_root)
    _require_idle_repository(target_root)
    return target_root


def _unborn_target_root(target: Path) -> Path:
    if not target.is_dir():
        raise ApplicationError(f"target directory does not exist: {target}")
    try:
        root = Path(_output(["git", "rev-parse", "--show-toplevel"], cwd=target)).resolve()
    except subprocess.CalledProcessError as error:
        raise ApplicationError(
            f"target must be an initialized Git repository: {target}"
        ) from error
    if target.resolve() != root:
        raise ApplicationError(f"target must be the Git repository root: {root}")
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if completed.returncode == 0:
        raise ApplicationError(
            f"target already has a commit; use apply-template instead: {root}"
        )
    return root


def _require_clean_repository(target: Path) -> None:
    status = _output_bytes(
        ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=target
    )
    if status:
        raise ApplicationError(f"target repository is not clean: {target}")


def _require_idle_repository(target: Path) -> None:
    for marker in (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "rebase-merge",
        "rebase-apply",
    ):
        if _git_path(target, marker).exists():
            raise ApplicationError(f"target repository has a Git operation in progress: {marker}")


def _git_path(repository: Path, marker: str) -> Path:
    return Path(
        _output(
            ["git", "rev-parse", "--path-format=absolute", "--git-path", marker],
            cwd=repository,
        )
    )


def _load_apply_config(path: Path) -> tuple[ApplyPolicy, tuple[str, ...]]:
    try:
        config = load_template_config(path)
    except ConfigurationError as error:
        raise ApplicationError(f"invalid fetched templates.toml: {error}") from error

    raw_templates = config.get("templates")
    if not isinstance(raw_templates, dict) or not raw_templates:
        raise ApplicationError("fetched templates.toml does not declare templates")
    raw_apply = config.get("apply")
    if not isinstance(raw_apply, dict):
        raise ApplicationError("fetched templates.toml does not declare [apply]")
    protected = raw_apply.get("protected")
    hints = raw_apply.get("hints", [])
    if not isinstance(protected, list) or not protected or not all(
        isinstance(pattern, str) and pattern and "/" not in pattern
        for pattern in protected
    ):
        raise ApplicationError("apply.protected must be root path patterns")
    if not isinstance(hints, list) or not all(isinstance(hint, str) for hint in hints):
        raise ApplicationError("apply.hints must be an array of strings")
    unknown = set(raw_apply) - {"protected", "hints"}
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ApplicationError(f"unknown [apply] keys: {names}")
    return ApplyPolicy(tuple(protected), tuple(hints)), tuple(raw_templates)


def _prepared_template_commit(
    prepared: Path,
    template: str,
    protected: tuple[str, ...],
    temporary: Path,
) -> tuple[str, tuple[str, ...], Path]:
    repository = temporary / "prepared.git"
    _run(["git", "init", "--bare", "--quiet", str(repository)])
    index = temporary / "prepared.index"
    environment = os.environ | {
        "GIT_DIR": str(repository),
        "GIT_INDEX_FILE": str(index),
        "GIT_WORK_TREE": str(prepared),
    }
    _run(["git", "read-tree", "--empty"], cwd=prepared, env=environment)
    _run(["git", "add", "--all"], cwd=prepared, env=environment)
    paths = _output_bytes(
        ["git", "ls-files", "--cached", "-z"], cwd=prepared, env=environment
    )
    decoded_paths = tuple(
        path.decode("utf-8") for path in paths.rstrip(b"\0").split(b"\0") if path
    )
    skipped = tuple(
        path
        for path in decoded_paths
        if "/" not in path
        and any(fnmatch.fnmatchcase(path, pattern) for pattern in protected)
    )
    if skipped:
        _run(
            ["git", "update-index", "--force-remove", "--", *skipped],
            cwd=prepared,
            env=environment,
        )
    tree = _output(["git", "write-tree"], cwd=prepared, env=environment)
    commit_environment = environment | {
        "GIT_AUTHOR_EMAIL": "template-tool@localhost",
        "GIT_AUTHOR_NAME": "template-tool",
        "GIT_COMMITTER_EMAIL": "template-tool@localhost",
        "GIT_COMMITTER_NAME": "template-tool",
    }
    filtered_commit = _output(
        ["git", "commit-tree", tree, "-m", f"Apply {template} template"],
        cwd=prepared,
        env=commit_environment,
    )
    return filtered_commit, skipped, repository


def _run(
    command: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _output(
    command: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _output_bytes(
    command: list[str], cwd: Path, env: dict[str, str] | None = None
) -> bytes:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
    ).stdout
