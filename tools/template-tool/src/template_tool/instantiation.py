from __future__ import annotations

import json
import keyword
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


TOKEN_PATTERN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
UPPERCASE_TOKEN_PATTERN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
GITHUB_OWNER_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
GITHUB_REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9._-]+")
PYTHON_PACKAGE_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SUPPORTED_METADATA_FIELDS = frozenset(
    {
        "project_name",
        "description",
        "github_owner",
        "repo_name",
        "python_package",
        "go_module",
        "cargo_package",
        "binary_name",
    }
)


class InstantiationError(ValueError):
    """Raised when metadata or a template tree violates the instantiation contract."""


@dataclass(frozen=True)
class InstantiationSpec:
    required: tuple[str, ...]
    tokens: dict[str, str]
    derived: dict[str, tuple[str, str]]
    validation_metadata: dict[str, str]
    export_metadata: dict[str, str]


def validate_metadata(metadata: dict[str, str], spec: InstantiationSpec) -> None:
    unknown = set(metadata) - set(spec.required)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise InstantiationError(f"metadata contains fields not required by this profile: {names}")
    missing = set(spec.required) - set(metadata)
    if missing:
        names = ", ".join(sorted(missing))
        raise InstantiationError(f"missing required metadata: {names}")
    for field, value in metadata.items():
        validate_metadata_value(field, value)


def validate_metadata_value(field: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise InstantiationError(f"metadata field {field!r} must be a non-empty string")
    if "\x00" in value or CONTROL_PATTERN.search(value):
        raise InstantiationError(f"metadata field {field!r} contains an ASCII control character")
    if value != value.strip():
        raise InstantiationError(f"metadata field {field!r} must not have leading or trailing whitespace")
    if "\n" in value or "\r" in value:
        raise InstantiationError(f"metadata field {field!r} must be a single line")
    if field == "github_owner" and not GITHUB_OWNER_PATTERN.fullmatch(value):
        raise InstantiationError(
            "metadata field 'github_owner' must be a valid GitHub owner name"
        )
    if field == "repo_name" and not GITHUB_REPOSITORY_PATTERN.fullmatch(value):
        raise InstantiationError(
            "metadata field 'repo_name' must be a valid GitHub repository name"
        )
    if field == "python_package" and (
        not PYTHON_PACKAGE_PATTERN.fullmatch(value) or keyword.iskeyword(value)
    ):
        raise InstantiationError(
            "metadata field 'python_package' must be a valid Python package identifier"
        )


def build_token_values(metadata: dict[str, str], spec: InstantiationSpec) -> dict[str, str]:
    validate_metadata(metadata, spec)
    values = {token: metadata[source] for token, source in spec.tokens.items()}
    for token, (source, transform) in spec.derived.items():
        value = metadata[source]
        if transform == "hyphen-to-underscore":
            values[token] = value.replace("-", "_")
        elif transform == "json-string":
            values[token] = json.dumps(value, ensure_ascii=False)
        elif transform == "toml-basic-string":
            values[token] = json.dumps(value, ensure_ascii=False)
        else:
            raise InstantiationError(f"unsupported derived transform: {transform}")
    return values


def instantiate_tree(root: Path | str, spec: InstantiationSpec, metadata: dict[str, str]) -> None:
    root = Path(root)
    values = build_token_values(metadata, spec)
    entries = _entries(root)
    source_paths = set(entries)
    plan: dict[PurePosixPath, PurePosixPath] = {}
    for source in entries:
        destination = _replace_path(source, values)
        if destination in source_paths and destination != source:
            raise InstantiationError(f"instantiation target already exists: {destination}")
        if destination in plan.values() and plan.get(source) != destination:
            raise InstantiationError(f"path collision after instantiation: {destination}")
        plan[source] = destination

    destination_kinds = {destination: entries[source] for source, destination in plan.items()}
    destinations = set(destination_kinds)
    for destination in destinations:
        for parent in destination.parents:
            if parent == PurePosixPath("."):
                break
            if parent in destinations and destination_kinds[parent] != "dir":
                raise InstantiationError(f"path type conflict after instantiation: {destination}")
    _materialize(root, entries, plan, values)


def _entries(root: Path) -> dict[PurePosixPath, str]:
    entries: dict[PurePosixPath, str] = {}
    for path in root.rglob("*"):
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if path.is_symlink():
            entries[relative] = "symlink"
        elif path.is_dir():
            entries[relative] = "dir"
        elif path.is_file():
            entries[relative] = "file"
    return entries


def _replace_path(path: PurePosixPath, values: dict[str, str]) -> PurePosixPath:
    parts: list[str] = []
    for component in path.parts:
        replaced = _replace_text(component, values)
        if replaced != component and not _safe_path_component(replaced):
            raise InstantiationError(f"unsafe path component after instantiation: {path}")
        parts.append(replaced)
    destination = PurePosixPath(*parts)
    if destination.is_absolute() or ".." in destination.parts:
        raise InstantiationError(f"instantiation path escapes staging root: {path}")
    return destination


def _safe_path_component(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and "/" not in value and "\\" not in value and not CONTROL_PATTERN.search(value)


def _replace_text(text: str, values: dict[str, str]) -> str:
    return TOKEN_PATTERN.sub(lambda match: values.get(match.group(1), match.group(0)), text)


def _materialize(
    root: Path,
    entries: dict[PurePosixPath, str],
    plan: dict[PurePosixPath, PurePosixPath],
    values: dict[str, str],
) -> None:
    replacement = Path(tempfile.mkdtemp(prefix=f".{root.name}.instantiate-", dir=root.parent))
    try:
        replacement.chmod(0o755)
        for source, kind in sorted(entries.items(), key=lambda item: (len(item[0].parts), str(item[0]))):
            destination = replacement.joinpath(*plan[source].parts)
            if kind == "dir":
                destination.mkdir(parents=True, exist_ok=True)
                destination.chmod((root / Path(*source.parts)).stat().st_mode & 0o7777)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            source_path = root.joinpath(*source.parts)
            if kind == "symlink":
                destination.symlink_to(os.readlink(source_path))
                continue
            content = source_path.read_bytes()
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            if text is not None:
                text = _replace_text(text, values)
                unknown = sorted(set(UPPERCASE_TOKEN_PATTERN.findall(text)))
                if unknown:
                    names = ", ".join(f"{{{{{name}}}}}" for name in unknown)
                    raise InstantiationError(f"unknown metadata token remains in {source}: {names}")
                content = text.encode("utf-8")
            destination.write_bytes(content)
            destination.chmod(source_path.stat().st_mode & 0o7777)
        for child in root.iterdir():
            if child != replacement:
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        for child in replacement.iterdir():
            child.rename(root / child.name)
    finally:
        if replacement.exists():
            shutil.rmtree(replacement)
