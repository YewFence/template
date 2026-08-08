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
    skipped: tuple[str, ...]
    hints: tuple[str, ...]
    conflicted: bool
    jujutsu: bool
    instantiated: bool


@dataclass(frozen=True)
class InitProjectResult:
    initial_commit: str
    application: ApplyResult


def initialize_project(
    repository: str,
    reference: str,
    template: str,
    target: Path | str,
    metadata: dict[str, str],
) -> InitProjectResult:
    _validate_template_name(template)
    target_root = _unborn_target_root(Path(target))
    _require_clean_repository(target_root)
    _require_idle_repository(target_root)
    _validate_metadata_for_template(repository, reference, template, metadata)
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
    try:
        application = _apply_template(
            repository, reference, template, target_root, metadata=metadata, protect=False
        )
    except (ApplicationError, subprocess.CalledProcessError) as error:
        raise ApplicationError(
            f"created initial commit {initial_commit}, but template application failed: {error}"
        ) from error
    return InitProjectResult(initial_commit, application)


def apply_template(
    repository: str,
    reference: str,
    template: str,
    target: Path | str,
    metadata: dict[str, str] | None = None,
    *,
    keep_tokens: bool = False,
) -> ApplyResult:
    _validate_template_name(template)
    if keep_tokens and metadata is not None:
        raise ApplicationError("--keep-tokens cannot be combined with metadata")
    if not keep_tokens:
        _validate_metadata_for_template(repository, reference, template, metadata or {})
    return _apply_template(
        repository,
        reference,
        template,
        target,
        metadata=None if keep_tokens else metadata,
        protect=True,
    )


def validate_apply_target(target: Path | str) -> None:
    """Validate that a target repository can safely accept template changes."""
    _validated_apply_target_root(Path(target))


def required_metadata(
    repository: str, reference: str, template: str
) -> tuple[str, ...]:
    _validate_template_name(template)
    with _fetched_template(repository, reference, template) as fetched:
        return fetched[2].required_metadata(template)


def _validate_metadata_for_template(
    repository: str,
    reference: str,
    template: str,
    metadata: dict[str, str],
) -> None:
    with _fetched_template(repository, reference, template) as fetched:
        _, _, repository_reader = fetched
        try:
            build_token_values(metadata, repository_reader.instantiation_spec(template))
        except (TemplateError, InstantiationError) as error:
            raise ApplicationError(f"cannot instantiate {template!r}: {error}") from error


def _apply_template(
    repository: str,
    reference: str,
    template: str,
    target: Path | str,
    *,
    metadata: dict[str, str] | None,
    protect: bool,
) -> ApplyResult:
    target_root = _validated_apply_target_root(Path(target))

    with tempfile.TemporaryDirectory(prefix="apply-template-") as temporary:
        source, commit, policy = _fetch_template(
            repository, reference, template, Path(temporary)
        )

        temporary_commit, skipped = _filtered_template_commit(
            source,
            commit,
            template,
            policy.protected if protect else (),
            Path(temporary),
            metadata,
        )

        _run(
            ["git", "fetch", "--quiet", "--no-tags", str(source), temporary_commit],
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
            repository=repository,
            template=template,
            reference=reference,
            commit=commit,
            skipped=skipped,
            hints=policy.hints if protect else (),
            conflicted=conflicted,
            jujutsu=(target_root / ".jj").exists(),
            instantiated=metadata is not None,
        )


@contextmanager
def _fetched_template(
    repository: str, reference: str, template: str
) -> Iterator[tuple[Path, str, TemplateRepository]]:
    with tempfile.TemporaryDirectory(prefix="template-contract-") as temporary:
        source, commit, _ = _fetch_template(
            repository, reference, template, Path(temporary)
        )
        repository_reader = TemplateRepository(source)
        yield source, commit, repository_reader


def _fetch_template(
    repository: str, reference: str, template: str, temporary: Path
) -> tuple[Path, str, ApplyPolicy]:
    source = temporary / "source"
    _run(["git", "init", "--quiet", str(source)])
    _run(["git", "remote", "add", "origin", repository], cwd=source)
    _run(["git", "sparse-checkout", "init", "--cone"], cwd=source)
    _run(
        [
            "git", "sparse-checkout", "set", "tools/template-tool", "scripts", "templates.toml", f"templates/{template}"
        ],
        cwd=source,
    )
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
    if template not in templates:
        choices = ", ".join(templates)
        raise ApplicationError(
            f"unknown template {template!r} at {commit}; expected one of: {choices}"
        )
    repository_reader.select(template)
    return source, commit, policy


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


def _filtered_template_commit(
    source: Path,
    commit: str,
    template: str,
    protected: tuple[str, ...],
    temporary: Path,
    metadata: dict[str, str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    treeish = f"{commit}:templates/{template}"
    try:
        paths = _output_bytes(
            ["git", "ls-tree", "-r", "--name-only", "-z", treeish], cwd=source
        )
    except subprocess.CalledProcessError as error:
        raise ApplicationError(
            f"template snapshot does not exist at {treeish}"
        ) from error
    decoded_paths = tuple(
        path.decode("utf-8") for path in paths.rstrip(b"\0").split(b"\0") if path
    )
    skipped = tuple(
        path
        for path in decoded_paths
        if "/" not in path
        and any(fnmatch.fnmatchcase(path, pattern) for pattern in protected)
    )

    index = temporary / "template.index"
    environment = os.environ | {"GIT_INDEX_FILE": str(index)}
    if metadata is not None:
        try:
            TemplateRepository(source).instantiate(
                template, source / "templates" / template, metadata
            )
        except TemplateError as error:
            raise ApplicationError(f"cannot instantiate {template!r}: {error}") from error
        environment["GIT_WORK_TREE"] = str(source / "templates" / template)
        _run(["git", "read-tree", "--empty"], cwd=source, env=environment)
        _run(
            ["git", "add", "--sparse", "--all"],
            cwd=source / "templates" / template,
            env=environment,
        )
    else:
        _run(["git", "read-tree", treeish], cwd=source, env=environment)
    if skipped:
        _run(
            ["git", "update-index", "--force-remove", "--", *skipped],
            cwd=source,
            env=environment,
        )
    tree = _output(["git", "write-tree"], cwd=source, env=environment)
    commit_environment = environment | {
        "GIT_AUTHOR_EMAIL": "template-tool@localhost",
        "GIT_AUTHOR_NAME": "template-tool",
        "GIT_COMMITTER_EMAIL": "template-tool@localhost",
        "GIT_COMMITTER_NAME": "template-tool",
    }
    filtered_commit = _output(
        ["git", "commit-tree", tree, "-m", f"Apply {template} template"],
        cwd=source,
        env=commit_environment,
    )
    return filtered_commit, skipped


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


def _output_bytes(command: list[str], cwd: Path) -> bytes:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
    ).stdout
