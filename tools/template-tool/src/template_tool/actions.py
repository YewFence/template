from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from .repository import TemplateError, TemplateRepository


WorkflowUpdater = Callable[[tuple[Path, ...]], None]


def update_actions(
    repository: TemplateRepository,
    updater: WorkflowUpdater,
    validate: Callable[[], None] | None = None,
) -> tuple[Path, ...]:
    sources = discover_action_sources(repository.root)
    if not sources:
        raise TemplateError("no action source files found")
    original = {path: path.read_bytes() for path in sources}

    with tempfile.TemporaryDirectory(prefix="actions-update-") as temporary:
        staging = Path(temporary)
        staged_paths: list[Path] = []
        for source in sources:
            relative = source.relative_to(repository.root)
            staged = staging / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged)
            staged_paths.append(staged)

        updater(tuple(staged_paths))
        staged_files = {
            path.relative_to(staging)
            for path in staging.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        expected_files = {path.relative_to(repository.root) for path in sources}
        if staged_files != expected_files:
            unexpected = staged_files - expected_files
            missing = expected_files - staged_files
            details = [
                *(f"unexpected path: {path}" for path in sorted(unexpected, key=str)),
                *(f"missing path: {path}" for path in sorted(missing, key=str)),
            ]
            raise TemplateError("actions updater changed its file set: " + ", ".join(details))

        updated: dict[Path, bytes] = {}
        for source, staged in zip(sources, staged_paths, strict=True):
            if staged.is_symlink() or not staged.is_file():
                raise TemplateError(
                    f"actions updater output must be a regular file: {source}"
                )
            content = staged.read_bytes()
            if content != original[source]:
                updated[source] = content

    for path, content in updated.items():
        path.write_bytes(content)
    try:
        _render_and_check(repository)
        if validate is not None:
            validate()
    except Exception:
        for path, content in original.items():
            path.write_bytes(content)
        _render_and_check(repository)
        raise
    return tuple(path.relative_to(repository.root) for path in updated)


def discover_action_sources(root: Path) -> tuple[Path, ...]:
    candidates: set[Path] = set()
    root_workflows = root / ".github" / "workflows"
    if root_workflows.is_dir():
        candidates.update(path for path in root_workflows.rglob("*") if path.is_file())
    for source_root in (root / "shared", root / "overlays"):
        if not source_root.is_dir():
            continue
        for path in source_root.rglob("*"):
            if path.is_file() and (
                ".github" in path.parts or "workflows" in path.parts
            ):
                candidates.add(path)

    suffixes = (".yml", ".yaml", ".yml.j2", ".yaml.j2")
    selected = tuple(
        sorted(
            (
                path
                for path in candidates
                if path.name.endswith(suffixes) and not path.is_symlink()
            ),
            key=lambda path: str(path.relative_to(root)),
        )
    )
    return selected


def _render_and_check(repository: TemplateRepository) -> None:
    repository.render_repository()
    for template in repository.template_names:
        repository.render(template)
    root_result = repository.check_repository()
    if not root_result.matches:
        raise TemplateError("repository generated files are not in sync")
    for template in repository.template_names:
        result = repository.check(template)
        if not result.matches:
            raise TemplateError(f"template {template!r} is not in sync")
