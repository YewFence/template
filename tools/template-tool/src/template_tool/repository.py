from __future__ import annotations

import difflib
import os
import posixpath
import shutil
import stat
import subprocess
import tempfile
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from collections.abc import Callable
from typing import Literal

from jinja2 import Environment, StrictUndefined, nodes


Owner = Literal["shared", "overlay"]
SourceKind = Literal["static", "layout"]
PathRule = Literal["shared", "overlay", "omit"]


class TemplateError(RuntimeError):
    """Raised when template sources or configuration violate the render contract."""


@dataclass(frozen=True)
class TemplateProfile:
    name: str
    path_rules: dict[PurePosixPath, PathRule]
    slots: dict[PurePosixPath, dict[str, tuple[str, ...]]]
    lock_outputs: tuple[PurePosixPath, ...]


@dataclass(frozen=True)
class Source:
    owner: Owner
    kind: SourceKind
    output_path: PurePosixPath
    source_path: Path


@dataclass(frozen=True)
class TreeEntry:
    kind: Literal["file", "symlink"]
    executable: bool
    content: bytes


@dataclass(frozen=True)
class RenderResult:
    template: str
    differences: tuple[str, ...] = ()

    @property
    def matches(self) -> bool:
        return not self.differences


class TemplateRepository:
    """Render and validate all templates behind one small repository interface."""

    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.config_path = self.root / "templates.toml"
        self.shared_root = self.root / "shared"
        self.overlays_root = self.root / "overlays"
        self.templates_root = self.root / "templates"
        self._profiles = self._load_profiles()
        self._environment = Environment(
            autoescape=False,
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            newline_sequence="\n",
            variable_start_string="<$",
            variable_end_string="$>",
            block_start_string="<%",
            block_end_string="%>",
            comment_start_string="<#",
            comment_end_string="#>",
        )

    @property
    def template_names(self) -> tuple[str, ...]:
        return tuple(self._profiles)

    def select(self, template: str | None) -> tuple[str, ...]:
        if template is None:
            return self.template_names
        if template not in self._profiles:
            choices = ", ".join(self.template_names)
            raise TemplateError(f"unknown template {template!r}; expected one of: {choices}")
        return (template,)

    def render(self, template: str) -> RenderResult:
        profile = self._profile(template)
        staged = self._build_staged_tree(profile)
        target = self.templates_root / template
        try:
            self._replace_tree(staged, target)
        except Exception:
            self._remove_path(staged)
            raise
        return RenderResult(template)

    def check(self, template: str) -> RenderResult:
        profile = self._profile(template)
        staged = self._build_staged_tree(profile)
        target = self.templates_root / template
        try:
            differences = tuple(self._compare_trees(staged, target))
        finally:
            self._remove_path(staged)
        return RenderResult(template, differences)

    def update_locks(
        self,
        template: str,
        bump: bool,
        run_adapter: Callable[[Path, bool], None],
        validate: Callable[[str], None] | None = None,
    ) -> None:
        profile = self._profile(template)
        outputs = set(profile.lock_outputs)
        if not outputs:
            raise TemplateError(f"template {template!r} has no locks.outputs")

        staged = self._build_staged_tree(profile)
        overlay_root = self.overlays_root / template
        overlay_static = overlay_root / "static"
        before = self._scan_tree(staged)
        try:
            run_adapter(staged, bump)
            after = self._scan_tree(staged)
            changes = self._tree_difference(before, after)
            changed_paths = {
                PurePosixPath(line.split(": ", 1)[1])
                for line in changes
                if ": " in line
            }
            unexpected = changed_paths - outputs
            if unexpected:
                paths = ", ".join(str(path) for path in sorted(unexpected, key=str))
                raise TemplateError(f"locks adapter changed undeclared paths: {paths}")
            self._validate_lock_outputs(staged, profile.lock_outputs)

            replacement = Path(
                tempfile.mkdtemp(prefix=f".locks-{template}-", dir=overlay_root)
            )
            self._remove_path(replacement)
            shutil.copytree(overlay_static, replacement, symlinks=True)
            for output in profile.lock_outputs:
                source = staged.joinpath(*output.parts)
                destination = replacement.joinpath(*output.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                self._remove_path(destination)
                shutil.copy2(source, destination, follow_symlinks=False)

            overlay_backup = overlay_root / f".static.backup-{uuid.uuid4().hex}"
            target = self.templates_root / template
            target_backup = self.templates_root / f".{template}.backup-{uuid.uuid4().hex}"
            target_existed = os.path.lexists(target)
            overlay_backup_created = False
            overlay_swapped = False
            target_backup_created = False
            try:
                os.replace(overlay_static, overlay_backup)
                overlay_backup_created = True
                os.replace(replacement, overlay_static)
                overlay_swapped = True
                if target_existed:
                    os.replace(target, target_backup)
                    target_backup_created = True
                self.render(template)
                result = self.check(template)
                if not result.matches:
                    details = "\n".join(result.differences)
                    raise TemplateError(f"rendered template is not in sync:\n{details}")
                if validate is not None:
                    validate(template)
            except Exception:
                if not target_existed or target_backup_created:
                    self._remove_path(target)
                if target_backup_created:
                    os.replace(target_backup, target)
                if overlay_swapped:
                    self._remove_path(overlay_static)
                if overlay_backup_created:
                    os.replace(overlay_backup, overlay_static)
                raise
            else:
                self._remove_path(target_backup)
                self._remove_path(overlay_backup)
        finally:
            self._remove_path(staged)

    @staticmethod
    def _validate_lock_outputs(
        staged: Path, outputs: tuple[PurePosixPath, ...]
    ) -> None:
        for output in outputs:
            path = staged.joinpath(*output.parts)
            if path.is_symlink() or not path.is_file():
                raise TemplateError(
                    f"locks output must be a regular file: {output}"
                )
            if path.stat(follow_symlinks=False).st_mode & stat.S_IXUSR:
                raise TemplateError(f"locks output must not be executable: {output}")

    def _profile(self, template: str) -> TemplateProfile:
        try:
            return self._profiles[template]
        except KeyError as error:
            choices = ", ".join(self.template_names)
            raise TemplateError(
                f"unknown template {template!r}; expected one of: {choices}"
            ) from error

    def _load_profiles(self) -> dict[str, TemplateProfile]:
        if not self.config_path.is_file():
            raise TemplateError(f"missing configuration: {self.config_path}")

        with self.config_path.open("rb") as config_file:
            config = tomllib.load(config_file)

        if config.get("version") != 1:
            raise TemplateError("templates.toml must declare version = 1")

        raw_templates = config.get("templates")
        if not isinstance(raw_templates, dict) or not raw_templates:
            raise TemplateError("templates.toml must declare at least one template")

        profiles: dict[str, TemplateProfile] = {}
        for name, raw_profile in raw_templates.items():
            if not isinstance(name, str) or not name:
                raise TemplateError("template names must be non-empty strings")
            if not isinstance(raw_profile, dict):
                raise TemplateError(f"templates.{name} must be a table")

            raw_paths = raw_profile.get("paths", {})
            if not isinstance(raw_paths, dict):
                raise TemplateError(f"templates.{name}.paths must be a table")
            path_rules: dict[PurePosixPath, PathRule] = {}
            for raw_path, raw_rule in raw_paths.items():
                output_path = self._validate_output_path(raw_path)
                if raw_rule not in {"shared", "overlay", "omit"}:
                    raise TemplateError(
                        f"templates.{name}.paths.{raw_path} must be shared, overlay, or omit"
                    )
                path_rules[output_path] = raw_rule

            raw_slots = raw_profile.get("slots", {})
            if not isinstance(raw_slots, dict):
                raise TemplateError(f"templates.{name}.slots must be a table")
            slots: dict[PurePosixPath, dict[str, tuple[str, ...]]] = {}
            for raw_path, raw_bindings in raw_slots.items():
                output_path = self._validate_output_path(raw_path)
                if not isinstance(raw_bindings, dict):
                    raise TemplateError(
                        f"templates.{name}.slots.{raw_path} must be a table"
                    )
                bindings: dict[str, tuple[str, ...]] = {}
                for slot_name, raw_fragments in raw_bindings.items():
                    if not isinstance(slot_name, str) or not slot_name:
                        raise TemplateError(f"invalid slot name for {name}:{raw_path}")
                    if not isinstance(raw_fragments, list) or not all(
                        isinstance(fragment, str) for fragment in raw_fragments
                    ):
                        raise TemplateError(
                            f"binding {name}:{raw_path}:{slot_name} must be an array of strings"
                        )
                    bindings[slot_name] = tuple(raw_fragments)
                slots[output_path] = bindings

            raw_locks = raw_profile.get("locks", {})
            if not isinstance(raw_locks, dict):
                raise TemplateError(f"templates.{name}.locks must be a table")
            raw_outputs = raw_locks.get("outputs", [])
            if not isinstance(raw_outputs, list) or not all(
                isinstance(output, str) for output in raw_outputs
            ):
                raise TemplateError(f"templates.{name}.locks.outputs must be an array of strings")
            lock_outputs = tuple(
                self._validate_output_path(output) for output in raw_outputs
            )
            if len(set(lock_outputs)) != len(lock_outputs):
                raise TemplateError(f"templates.{name}.locks.outputs must not repeat paths")

            unknown_keys = set(raw_profile) - {"paths", "slots", "locks"}
            if unknown_keys:
                keys = ", ".join(sorted(unknown_keys))
                raise TemplateError(f"unknown keys in templates.{name}: {keys}")

            profiles[name] = TemplateProfile(name, path_rules, slots, lock_outputs)

        return profiles

    @staticmethod
    def _validate_output_path(raw_path: object) -> PurePosixPath:
        if not isinstance(raw_path, str) or not raw_path:
            raise TemplateError("output paths must be non-empty strings")
        if "\\" in raw_path:
            raise TemplateError(f"output path must use forward slashes: {raw_path!r}")
        path = PurePosixPath(raw_path)
        if path.is_absolute() or path == PurePosixPath(".") or ".." in path.parts:
            raise TemplateError(f"output path escapes the template root: {raw_path!r}")
        return path

    def _build_staged_tree(self, profile: TemplateProfile) -> Path:
        overlay_root = self.overlays_root / profile.name
        if not overlay_root.is_dir():
            raise TemplateError(f"missing overlay for template {profile.name!r}")

        self.templates_root.mkdir(parents=True, exist_ok=True)
        staged = Path(
            tempfile.mkdtemp(
                prefix=f".render-{profile.name}-", dir=self.templates_root
            )
        )
        try:
            sources = self._select_sources(profile, overlay_root)
            self._validate_output_tree(sources)
            for output_path in sorted(sources, key=str):
                self._render_source(
                    profile,
                    sources[output_path],
                    staged / Path(*output_path.parts),
                    overlay_root,
                )

            unused_bindings = set(profile.slots) - {
                path for path, source in sources.items() if source.kind == "layout"
            }
            if unused_bindings:
                paths = ", ".join(str(path) for path in sorted(unused_bindings, key=str))
                raise TemplateError(
                    f"template {profile.name!r} has slot bindings for non-layout paths: {paths}"
                )
            return staged
        except Exception:
            self._remove_path(staged)
            raise

    def _select_sources(
        self, profile: TemplateProfile, overlay_root: Path
    ) -> dict[PurePosixPath, Source]:
        shared = self._discover_owner("shared", self.shared_root)
        overlay = self._discover_owner("overlay", overlay_root)
        selected: dict[PurePosixPath, Source] = {}
        consumed_rules: set[PurePosixPath] = set()

        for output_path in sorted(set(shared) | set(overlay), key=str):
            shared_source = shared.get(output_path)
            overlay_source = overlay.get(output_path)
            rule = profile.path_rules.get(output_path)

            if shared_source is not None and overlay_source is not None:
                if rule is None:
                    raise TemplateError(
                        f"template {profile.name!r} has an unresolved shared/overlay conflict at {output_path}"
                    )
                consumed_rules.add(output_path)
                if rule == "shared":
                    selected[output_path] = shared_source
                elif rule == "overlay":
                    selected[output_path] = overlay_source
                continue

            source = shared_source or overlay_source
            if source is None:
                continue
            if rule is None:
                selected[output_path] = source
                continue

            consumed_rules.add(output_path)
            if rule == "omit":
                continue
            raise TemplateError(
                f"template {profile.name!r} has redundant {rule!r} rule for single-source path {output_path}"
            )

        stale_rules = set(profile.path_rules) - consumed_rules
        if stale_rules:
            paths = ", ".join(str(path) for path in sorted(stale_rules, key=str))
            raise TemplateError(
                f"template {profile.name!r} has path rules for missing sources: {paths}"
            )
        return selected

    def _discover_owner(
        self, owner: Owner, owner_root: Path
    ) -> dict[PurePosixPath, Source]:
        sources: dict[PurePosixPath, Source] = {}
        for kind in ("static", "layout"):
            source_root = owner_root / ("static" if kind == "static" else "layouts")
            if not source_root.exists():
                continue
            if not source_root.is_dir():
                raise TemplateError(f"source root is not a directory: {source_root}")

            for source_path, relative_path in self._walk_source_tree(source_root):
                if kind == "layout":
                    if source_path.is_symlink():
                        raise TemplateError(f"layout cannot be a symlink: {source_path}")
                    if relative_path.suffix != ".j2":
                        raise TemplateError(
                            f"layout path must end in .j2: {source_path}"
                        )
                    output_path = relative_path.with_suffix("")
                else:
                    output_path = relative_path

                if output_path in sources:
                    previous = sources[output_path]
                    raise TemplateError(
                        f"{owner} has both {previous.kind} and {kind} sources for {output_path}"
                    )
                sources[output_path] = Source(
                    owner, kind, output_path, source_path
                )
        return sources

    @classmethod
    def _walk_source_tree(
        cls, root: Path, relative: PurePosixPath = PurePosixPath()
    ):
        for entry in sorted(os.scandir(root), key=lambda item: item.name):
            entry_path = Path(entry.path)
            entry_relative = relative / entry.name
            if entry.is_symlink() or entry.is_file(follow_symlinks=False):
                yield entry_path, entry_relative
            elif entry.is_dir(follow_symlinks=False):
                yield from cls._walk_source_tree(entry_path, entry_relative)
            else:
                raise TemplateError(f"unsupported source type: {entry_path}")

    @staticmethod
    def _validate_output_tree(sources: dict[PurePosixPath, Source]) -> None:
        output_paths = set(sources)
        for output_path in output_paths:
            parent = output_path.parent
            while parent != PurePosixPath("."):
                if parent in output_paths:
                    raise TemplateError(
                        f"output path {parent} conflicts with child path {output_path}"
                    )
                parent = parent.parent

    def _render_source(
        self,
        profile: TemplateProfile,
        source: Source,
        destination: Path,
        overlay_root: Path,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.kind == "static":
            self._copy_static(source.source_path, source.output_path, destination)
            return

        bindings = profile.slots.get(source.output_path, {})
        rendered = self._render_layout(
            profile.name, source.source_path, bindings, overlay_root
        )
        destination.write_bytes(rendered.encode("utf-8"))
        self._apply_git_mode(source.source_path, destination)

    def _copy_static(
        self, source: Path, output_path: PurePosixPath, destination: Path
    ) -> None:
        if source.is_symlink():
            target = os.readlink(source)
            self._validate_symlink(output_path, target)
            os.symlink(target, destination)
            return
        destination.write_bytes(source.read_bytes())
        self._apply_git_mode(source, destination)

    @staticmethod
    def _apply_git_mode(source: Path, destination: Path) -> None:
        executable = bool(source.stat(follow_symlinks=False).st_mode & stat.S_IXUSR)
        destination.chmod(0o755 if executable else 0o644)

    @staticmethod
    def _validate_symlink(output_path: PurePosixPath, target: str) -> None:
        if os.path.isabs(target):
            raise TemplateError(f"absolute output symlink is forbidden: {output_path}")
        normalized = posixpath.normpath(str(output_path.parent / target))
        if normalized == ".." or normalized.startswith("../"):
            raise TemplateError(f"output symlink escapes template root: {output_path}")

    def _render_layout(
        self,
        template_name: str,
        layout_path: Path,
        bindings: dict[str, tuple[str, ...]],
        overlay_root: Path,
    ) -> str:
        layout_source = layout_path.read_text(encoding="utf-8")
        parsed = self._environment.parse(layout_source)
        if any(True for _ in parsed.find_all(nodes.Extends)):
            raise TemplateError(f"layout cannot use Jinja extends: {layout_path}")

        declared_slots: set[str] = set()

        def slot(name: str, optional: bool = False) -> str:
            if not isinstance(name, str) or not name:
                raise TemplateError(f"invalid slot declaration in {layout_path}")
            if name in declared_slots:
                raise TemplateError(f"duplicate slot declaration {name!r} in {layout_path}")
            if not isinstance(optional, bool):
                raise TemplateError(
                    f"slot {name!r} optional flag must be boolean in {layout_path}"
                )
            declared_slots.add(name)
            fragments = bindings.get(name, ())
            if not fragments and not optional:
                raise TemplateError(
                    f"template {template_name!r} does not bind required slot {name!r} in {layout_path}"
                )
            return "".join(
                self._render_fragment(reference, overlay_root) for reference in fragments
            )

        template = self._environment.from_string(layout_source)
        rendered = template.render(slot=slot)
        unknown_slots = set(bindings) - declared_slots
        if unknown_slots:
            names = ", ".join(sorted(unknown_slots))
            raise TemplateError(
                f"template {template_name!r} binds unknown slots in {layout_path}: {names}"
            )
        return rendered

    def _render_fragment(self, reference: str, overlay_root: Path) -> str:
        owner, separator, raw_path = reference.partition(":")
        if separator != ":" or owner not in {"shared", "overlay"}:
            raise TemplateError(
                f"fragment reference must use shared: or overlay: namespace: {reference!r}"
            )
        fragment_path = self._validate_output_path(raw_path)
        if fragment_path.suffix != ".j2":
            raise TemplateError(f"fragment path must end in .j2: {reference!r}")

        fragment_root = (
            self.shared_root / "fragments"
            if owner == "shared"
            else overlay_root / "fragments"
        )
        candidate = fragment_root.joinpath(*fragment_path.parts)
        try:
            resolved_root = fragment_root.resolve(strict=True)
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (FileNotFoundError, ValueError) as error:
            raise TemplateError(f"invalid fragment reference: {reference!r}") from error
        if not resolved.is_file():
            raise TemplateError(f"fragment is not a file: {reference!r}")

        fragment_source = resolved.read_text(encoding="utf-8")
        parsed = self._environment.parse(fragment_source)
        if any(True for _ in parsed.find_all(nodes.Extends)):
            raise TemplateError(f"fragment cannot use Jinja extends: {reference!r}")
        return self._environment.from_string(fragment_source).render()

    @classmethod
    def _scan_tree(cls, root: Path) -> dict[PurePosixPath, TreeEntry]:
        if not root.is_dir():
            return {}
        entries: dict[PurePosixPath, TreeEntry] = {}
        for path, relative in cls._walk_source_tree(root):
            if path.is_symlink():
                entries[relative] = TreeEntry(
                    "symlink", False, os.readlink(path).encode("utf-8")
                )
            else:
                executable = bool(
                    path.stat(follow_symlinks=False).st_mode & stat.S_IXUSR
                )
                entries[relative] = TreeEntry("file", executable, path.read_bytes())
        return entries

    @classmethod
    def _compare_trees(cls, expected: Path, actual: Path) -> list[str]:
        expected_entries = cls._scan_tree(expected)
        actual_entries = cls._scan_tree(actual)
        extra_paths = set(actual_entries) - set(expected_entries)
        ignored_extras = cls._ignored_paths(actual, extra_paths)
        actual_entries = {
            path: entry
            for path, entry in actual_entries.items()
            if path not in ignored_extras
        }
        differences: list[str] = []
        for path in sorted(set(expected_entries) | set(actual_entries), key=str):
            expected_entry = expected_entries.get(path)
            actual_entry = actual_entries.get(path)
            if expected_entry is None:
                differences.append(f"unexpected path: {path}")
                continue
            if actual_entry is None:
                differences.append(f"missing path: {path}")
                continue
            if expected_entry.kind != actual_entry.kind:
                differences.append(
                    f"type mismatch: {path} ({actual_entry.kind} != {expected_entry.kind})"
                )
                continue
            if expected_entry.executable != actual_entry.executable:
                differences.append(f"executable bit mismatch: {path}")
            if expected_entry.content != actual_entry.content:
                differences.extend(cls._content_diff(path, expected_entry, actual_entry))
        return differences

    @classmethod
    def _tree_difference(
        cls, expected: dict[PurePosixPath, TreeEntry], actual: dict[PurePosixPath, TreeEntry]
    ) -> list[str]:
        differences: list[str] = []
        for path in sorted(set(expected) | set(actual), key=str):
            expected_entry = expected.get(path)
            actual_entry = actual.get(path)
            if expected_entry is None:
                differences.append(f"unexpected path: {path}")
            elif actual_entry is None:
                differences.append(f"missing path: {path}")
            elif expected_entry != actual_entry:
                differences.append(f"modified path: {path}")
        return differences

    @staticmethod
    def _ignored_paths(
        work_tree: Path, paths: set[PurePosixPath]
    ) -> set[PurePosixPath]:
        if not paths or not (work_tree / ".gitignore").is_file():
            return set()
        with tempfile.TemporaryDirectory(prefix="template-tool-ignore-") as temporary:
            git_dir = Path(temporary) / "repo.git"
            subprocess.run(
                ["git", "init", "--bare", "--quiet", str(git_dir)], check=True
            )
            environment = os.environ | {
                "GIT_DIR": str(git_dir),
                "GIT_WORK_TREE": str(work_tree),
            }
            raw_paths = b"\0".join(str(path).encode() for path in paths) + b"\0"
            completed = subprocess.run(
                ["git", "check-ignore", "--no-index", "--stdin", "-z"],
                env=environment,
                input=raw_paths,
                capture_output=True,
                check=False,
            )
            if completed.returncode not in {0, 1}:
                message = completed.stderr.decode(errors="replace").strip()
                raise TemplateError(f"git check-ignore failed: {message}")
            return {
                PurePosixPath(path.decode())
                for path in completed.stdout.rstrip(b"\0").split(b"\0")
                if path
            }

    @staticmethod
    def _content_diff(
        path: PurePosixPath, expected: TreeEntry, actual: TreeEntry
    ) -> list[str]:
        if expected.kind == "symlink":
            return [
                f"symlink target mismatch: {path} "
                f"({actual.content.decode()!r} != {expected.content.decode()!r})"
            ]
        try:
            expected_text = expected.content.decode("utf-8").splitlines(keepends=True)
            actual_text = actual.content.decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            return [f"binary content mismatch: {path}"]
        return [
            line.rstrip("\n")
            for line in difflib.unified_diff(
                actual_text,
                expected_text,
                fromfile=f"templates/{path}",
                tofile=f"expected/{path}",
            )
        ]

    @classmethod
    def _replace_tree(cls, staged: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
        target_existed = os.path.lexists(target)
        if target_existed:
            os.replace(target, backup)
        try:
            os.replace(staged, target)
        except Exception:
            if target_existed:
                os.replace(backup, target)
            raise
        if target_existed:
            cls._remove_path(backup)

    @staticmethod
    def _remove_path(path: Path) -> None:
        if not os.path.lexists(path):
            return
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
