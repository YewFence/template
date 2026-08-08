from __future__ import annotations

import difflib
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from jinja2 import Environment, StrictUndefined, nodes

from .capabilities import (
    CapabilityError,
    resolve_capabilities,
    validate_capabilities,
)
from .configuration import ConfigurationError, load_template_config
from .instantiation import (
    InstantiationError,
    InstantiationSpec,
    SUPPORTED_METADATA_FIELDS,
    build_token_values,
    instantiate_tree,
    validate_metadata,
)


Owner = Literal["shared", "overlay"]
SourceKind = Literal["static", "layout"]
PathRule = Literal["shared", "overlay", "omit"]


class TemplateError(RuntimeError):
    """Raised when template sources or configuration violate the render contract."""


@dataclass(frozen=True)
class TemplateProfile:
    name: str
    capabilities: dict[str, bool]
    capability_outputs: dict[str, tuple[tuple[PurePosixPath, bool], ...]]
    path_rules: dict[PurePosixPath, PathRule]
    slots: dict[PurePosixPath, dict[str, SlotBinding]]
    instantiation: InstantiationSpec


@dataclass(frozen=True)
class SlotBinding:
    capability: str | None
    fragments: tuple[str, ...]
    default_fragments: tuple[str, ...] | None = None

    def select(self, enabled_capabilities: frozenset[str]) -> tuple[str, ...]:
        if self.capability is None or self.capability in enabled_capabilities:
            return self.fragments
        return self.default_fragments or ()


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
        self.config_root = self.root / "config"
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
        capabilities = self.resolve_capabilities(template)
        staged = self._build_staged_tree(profile, frozenset(capabilities))
        target = self.templates_root / template
        try:
            self._replace_tree(staged, target)
        except Exception:
            self._remove_path(staged)
            raise
        return RenderResult(template)

    def render_to(
        self,
        template: str,
        destination: Path | str,
        *,
        enabled_capabilities: tuple[str, ...] | None = None,
    ) -> RenderResult:
        profile = self._profile(template)
        if enabled_capabilities is None:
            effective = self.resolve_capabilities(template)
        else:
            requested = set(enabled_capabilities)
            effective = self.resolve_capabilities(
                template,
                enable=enabled_capabilities,
                disable=tuple(set(profile.capabilities) - requested),
            )
        target = Path(destination).resolve()
        self._validate_render_destination(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        staged = self._build_staged_tree(
            profile, frozenset(effective), staging_parent=target.parent
        )
        try:
            self._replace_tree(staged, target)
        except Exception:
            self._remove_path(staged)
            raise
        return RenderResult(template)

    def _validate_render_destination(self, destination: Path) -> None:
        if destination.is_relative_to(self.root) or self.root.is_relative_to(
            destination
        ):
            raise TemplateError(
                "render destination must be outside repository-owned paths"
            )

    def render_repository(self) -> RenderResult:
        rendered = self._render_renovate_config(
            self.config_root / "renovate" / "monorepo.json"
        )
        if rendered is None:
            return RenderResult("repository")
        target = self.root / "renovate.json"
        temporary = self.root / f".renovate.json.{uuid.uuid4().hex}"
        temporary.write_bytes(rendered)
        temporary.chmod(0o644)
        os.replace(temporary, target)
        return RenderResult("repository")

    def check_repository(self) -> RenderResult:
        rendered = self._render_renovate_config(
            self.config_root / "renovate" / "monorepo.json"
        )
        if rendered is None:
            return RenderResult("repository")
        target = self.root / "renovate.json"
        expected = TreeEntry("file", False, rendered)
        if target.is_symlink() or not target.is_file():
            return RenderResult("repository", ("missing or invalid path: renovate.json",))
        actual = TreeEntry(
            "file",
            bool(target.stat(follow_symlinks=False).st_mode & stat.S_IXUSR),
            target.read_bytes(),
        )
        if expected == actual:
            return RenderResult("repository")
        differences = tuple(
            self._content_diff(PurePosixPath("renovate.json"), expected, actual)
        )
        if expected.executable != actual.executable:
            differences = ("executable bit mismatch: renovate.json", *differences)
        return RenderResult("repository", differences)

    def check(self, template: str) -> RenderResult:
        profile = self._profile(template)
        capabilities = self.resolve_capabilities(template)
        staged = self._build_staged_tree(profile, frozenset(capabilities))
        target = self.templates_root / template
        try:
            differences = tuple(self._compare_trees(staged, target))
        finally:
            self._remove_path(staged)
        return RenderResult(template, differences)

    def validation_metadata(self, template: str) -> dict[str, str]:
        return dict(self._profile(template).instantiation.validation_metadata)

    def capabilities(self, template: str) -> tuple[tuple[str, bool], ...]:
        return tuple(sorted(self._profile(template).capabilities.items()))

    def resolve_capabilities(
        self,
        template: str,
        *,
        enable: tuple[str, ...] = (),
        disable: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        try:
            return resolve_capabilities(
                self._profile(template).capabilities,
                enable=enable,
                disable=disable,
            )
        except CapabilityError as error:
            raise TemplateError(str(error)) from error

    def required_metadata(self, template: str) -> tuple[str, ...]:
        return self._profile(template).instantiation.required

    def instantiation_spec(self, template: str) -> InstantiationSpec:
        return self._profile(template).instantiation

    def instantiate(self, template: str, root: Path | str, metadata: dict[str, str]) -> None:
        try:
            instantiate_tree(Path(root), self._profile(template).instantiation, metadata)
        except InstantiationError as error:
            raise TemplateError(str(error)) from error

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

        try:
            config = load_template_config(self.config_path)
        except ConfigurationError as error:
            raise TemplateError(str(error)) from error

        raw_templates = config.get("templates")
        if not isinstance(raw_templates, dict) or not raw_templates:
            raise TemplateError("templates.toml must declare at least one template")

        profiles: dict[str, TemplateProfile] = {}
        for name, raw_profile in raw_templates.items():
            if not isinstance(name, str) or not name:
                raise TemplateError("template names must be non-empty strings")
            if not isinstance(raw_profile, dict):
                raise TemplateError(f"templates.{name} must be a table")

            unknown_keys = set(raw_profile) - {
                "capabilities",
                "capability_outputs",
                "paths",
                "slots",
                "instantiation",
            }
            if unknown_keys:
                keys = ", ".join(sorted(unknown_keys))
                raise TemplateError(f"unknown keys in templates.{name}: {keys}")

            try:
                capabilities = validate_capabilities(
                    raw_profile.get("capabilities"), name
                )
            except CapabilityError as error:
                raise TemplateError(str(error)) from error

            raw_capability_outputs = raw_profile.get("capability_outputs", {})
            if not isinstance(raw_capability_outputs, dict):
                raise TemplateError(
                    f"templates.{name}.capability_outputs must be a table"
                )
            capability_outputs: dict[
                str, tuple[tuple[PurePosixPath, bool], ...]
            ] = {}
            for capability, raw_selectors in raw_capability_outputs.items():
                if capability not in capabilities:
                    raise TemplateError(
                        f"templates.{name}.capability_outputs references undeclared capability: {capability}"
                    )
                if not isinstance(raw_selectors, list) or not raw_selectors:
                    raise TemplateError(
                        f"templates.{name}.capability_outputs.{capability} must be a non-empty array of strings"
                    )
                selectors: list[tuple[PurePosixPath, bool]] = []
                for raw_selector in raw_selectors:
                    if not isinstance(raw_selector, str) or not raw_selector:
                        raise TemplateError(
                            f"templates.{name}.capability_outputs.{capability} must be a non-empty array of strings"
                        )
                    if any(character in raw_selector for character in "*?["):
                        raise TemplateError(
                            f"templates.{name}.capability_outputs.{capability} must not use glob syntax: {raw_selector!r}"
                        )
                    is_prefix = raw_selector.endswith("/")
                    selector = self._validate_output_path(raw_selector.rstrip("/"))
                    selectors.append((selector, is_prefix))
                capability_outputs[capability] = tuple(selectors)

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
            slots: dict[PurePosixPath, dict[str, SlotBinding]] = {}
            for raw_path, raw_bindings in raw_slots.items():
                output_path = self._validate_output_path(raw_path)
                if not isinstance(raw_bindings, dict):
                    raise TemplateError(
                        f"templates.{name}.slots.{raw_path} must be a table"
                    )
                bindings: dict[str, SlotBinding] = {}
                for slot_name, raw_binding in raw_bindings.items():
                    if not isinstance(slot_name, str) or not slot_name:
                        raise TemplateError(f"invalid slot name for {name}:{raw_path}")
                    bindings[slot_name] = self._load_slot_binding(
                        name, raw_path, slot_name, raw_binding, capabilities
                    )
                slots[output_path] = bindings

            raw_instantiation = raw_profile.get("instantiation")
            if not isinstance(raw_instantiation, dict):
                raise TemplateError(f"templates.{name}.instantiation must be a table")
            required = raw_instantiation.get("required")
            tokens = raw_instantiation.get("tokens")
            derived = raw_instantiation.get("derived", {})
            raw_validation = raw_instantiation.get("validation")
            if not isinstance(required, list) or not all(isinstance(field, str) and field for field in required):
                raise TemplateError(f"templates.{name}.instantiation.required must be an array of strings")
            if len(set(required)) != len(required):
                raise TemplateError(f"templates.{name}.instantiation.required must not repeat fields")
            unsupported_fields = set(required) - SUPPORTED_METADATA_FIELDS
            if unsupported_fields:
                fields = ", ".join(sorted(unsupported_fields))
                raise TemplateError(f"templates.{name}.instantiation requires unsupported metadata fields: {fields}")
            if not isinstance(tokens, dict) or not all(isinstance(token, str) and isinstance(source, str) for token, source in tokens.items()):
                raise TemplateError(f"templates.{name}.instantiation.tokens must be a string map")
            invalid_tokens = [token for token in tokens if not re.fullmatch(r"[A-Z][A-Z0-9_]*", token)]
            if invalid_tokens:
                raise TemplateError(f"templates.{name}.instantiation.tokens contains invalid token names")
            if not isinstance(derived, dict):
                raise TemplateError(f"templates.{name}.instantiation.derived must be a table")
            derived_values: dict[str, tuple[str, str]] = {}
            for token, declaration in derived.items():
                if not isinstance(token, str) or not isinstance(declaration, dict):
                    raise TemplateError(f"invalid derived declaration for templates.{name}: {token}")
                source = declaration.get("source")
                transform = declaration.get("transform")
                if not isinstance(source, str) or not isinstance(transform, str):
                    raise TemplateError(f"derived {name}:{token} requires source and transform")
                derived_values[token] = (source, transform)
            if set(tokens) & set(derived_values):
                raise TemplateError(f"templates.{name}.instantiation token names must be unique")
            if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", token) for token in derived_values):
                raise TemplateError(f"templates.{name}.instantiation.derived contains invalid token names")
            if not isinstance(raw_validation, dict):
                raise TemplateError(f"templates.{name}.instantiation.validation must be a table")
            validation_metadata = raw_validation.get("metadata")
            if not isinstance(validation_metadata, dict) or not all(isinstance(field, str) and isinstance(value, str) for field, value in validation_metadata.items()):
                raise TemplateError(f"templates.{name}.instantiation.validation.metadata must be a string map")
            unknown_instantiation = set(raw_instantiation) - {"required", "tokens", "derived", "validation"}
            if unknown_instantiation:
                keys = ", ".join(sorted(unknown_instantiation))
                raise TemplateError(f"unknown keys in templates.{name}.instantiation: {keys}")
            spec = InstantiationSpec(tuple(required), dict(tokens), derived_values, dict(validation_metadata))
            referenced_fields = set(spec.tokens.values()) | {
                source for source, _ in spec.derived.values()
            }
            if referenced_fields - set(spec.required):
                raise TemplateError(f"templates.{name}.instantiation references undeclared metadata fields")
            try:
                validate_metadata(spec.validation_metadata, spec)
                build_token_values(spec.validation_metadata, spec)
            except InstantiationError as error:
                raise TemplateError(f"invalid validation metadata for {name}: {error}") from error

            profiles[name] = TemplateProfile(
                name, capabilities, capability_outputs, path_rules, slots, spec
            )

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

    @staticmethod
    def _load_slot_binding(
        template: str,
        output_path: str,
        slot_name: str,
        raw_binding: object,
        capabilities: dict[str, bool],
    ) -> SlotBinding:
        label = f"binding {template}:{output_path}:{slot_name}"
        if isinstance(raw_binding, list):
            if not all(isinstance(fragment, str) for fragment in raw_binding):
                raise TemplateError(f"{label} must be an array of strings")
            return SlotBinding(None, tuple(raw_binding))
        if not isinstance(raw_binding, dict):
            raise TemplateError(f"{label} must be an array or table")

        unknown = set(raw_binding) - {
            "capability",
            "fragments",
            "default_fragments",
        }
        if unknown:
            names = ", ".join(sorted(unknown))
            raise TemplateError(f"{label} contains unknown keys: {names}")
        capability = raw_binding.get("capability")
        if not isinstance(capability, str) or capability not in capabilities:
            raise TemplateError(f"{label} references undeclared capability: {capability}")
        fragments = raw_binding.get("fragments")
        if not isinstance(fragments, list) or not fragments or not all(
            isinstance(fragment, str) for fragment in fragments
        ):
            raise TemplateError(f"{label}.fragments must be a non-empty array of strings")
        raw_default = raw_binding.get("default_fragments")
        if "default_fragments" in raw_binding and (
            not isinstance(raw_default, list)
            or not raw_default
            or not all(isinstance(fragment, str) for fragment in raw_default)
        ):
            raise TemplateError(
                f"{label}.default_fragments must be a non-empty array of strings"
            )
        default_fragments = (
            tuple(raw_default) if isinstance(raw_default, list) else None
        )
        return SlotBinding(capability, tuple(fragments), default_fragments)

    def _build_staged_tree(
        self,
        profile: TemplateProfile,
        enabled_capabilities: frozenset[str],
        *,
        staging_parent: Path | None = None,
    ) -> Path:
        overlay_root = self.overlays_root / profile.name
        if not overlay_root.is_dir():
            raise TemplateError(f"missing overlay for template {profile.name!r}")

        staging_root = staging_parent or self.templates_root
        staging_root.mkdir(parents=True, exist_ok=True)
        staged = Path(
            tempfile.mkdtemp(
                prefix=f".render-{profile.name}-", dir=staging_root
            )
        )
        staged.chmod(0o755)
        try:
            sources = self._select_sources(profile, overlay_root)
            self._validate_output_tree(sources)
            for source in sources.values():
                if source.kind == "static" and source.source_path.is_symlink():
                    self._validate_symlink(
                        source.output_path, os.readlink(source.source_path)
                    )
            renovate = self._render_renovate_config(
                overlay_root / "fragments" / "renovate" / "profile.json"
            )
            renovate_path = PurePosixPath("renovate.json")
            if renovate is not None and renovate_path in sources:
                raise TemplateError(
                    f"template {profile.name!r} has a source that conflicts with the Renovate module"
                )
            output_paths = set(sources)
            if renovate is not None:
                output_paths.add(renovate_path)
            self._validate_capability_contract(profile, output_paths)
            all_capabilities = frozenset(profile.capabilities)
            for source in sources.values():
                if source.kind == "layout":
                    self._render_layout(
                        profile.name,
                        source.source_path,
                        profile.slots.get(source.output_path, {}),
                        overlay_root,
                        all_capabilities,
                    )
            selected_sources = {
                path: source
                for path, source in sources.items()
                if self._output_enabled(profile, path, enabled_capabilities)
            }
            for output_path in sorted(selected_sources, key=str):
                self._render_source(
                    profile,
                    selected_sources[output_path],
                    staged / Path(*output_path.parts),
                    overlay_root,
                    enabled_capabilities,
                )

            if renovate is not None and self._output_enabled(
                profile, renovate_path, enabled_capabilities
            ):
                destination = staged / "renovate.json"
                destination.write_bytes(renovate)
                destination.chmod(0o644)

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

    @staticmethod
    def _validate_capability_contract(
        profile: TemplateProfile, output_paths: set[PurePosixPath]
    ) -> None:
        matched_outputs: dict[PurePosixPath, list[tuple[str, PurePosixPath]]] = {}
        effects = {
            binding.capability
            for bindings in profile.slots.values()
            for binding in bindings.values()
            if binding.capability is not None
        }
        for capability, selectors in profile.capability_outputs.items():
            effects.add(capability)
            for selector, is_prefix in selectors:
                matches = {
                    output_path
                    for output_path in output_paths
                    if (not is_prefix and output_path == selector)
                    or (is_prefix and selector in output_path.parents)
                }
                if not matches:
                    suffix = "/" if is_prefix else ""
                    raise TemplateError(
                        f"capability output selector {selector}{suffix} does not match any output"
                    )
                for output_path in matches:
                    matched_outputs.setdefault(output_path, []).append(
                        (capability, selector)
                    )
        overlapping = {
            output_path: matches
            for output_path, matches in matched_outputs.items()
            if len(matches) > 1
        }
        if overlapping:
            output_path = min(overlapping, key=str)
            raise TemplateError(
                f"output {output_path} is matched by multiple capability output selectors"
            )
        empty = set(profile.capabilities) - effects
        if empty:
            names = ", ".join(sorted(empty))
            raise TemplateError(f"capability has no delivery effect: {names}")

    @staticmethod
    def _output_enabled(
        profile: TemplateProfile,
        output_path: PurePosixPath,
        enabled_capabilities: frozenset[str],
    ) -> bool:
        for capability, selectors in profile.capability_outputs.items():
            for selector, is_prefix in selectors:
                if (not is_prefix and output_path == selector) or (
                    is_prefix and selector in output_path.parents
                ):
                    return capability in enabled_capabilities
        return True

    def _render_renovate_config(self, profile_path: Path) -> bytes | None:
        base_path = self.shared_root / "renovate" / "base.json"
        if not base_path.exists():
            return None
        base = self._load_json_object(base_path, "Renovate base")
        profile = self._load_json_object(profile_path, "Renovate profile")
        base_rules = base.pop("packageRules", [])
        profile_rules = profile.pop("packageRules", [])
        self._validate_package_rules(base_rules, base_path)
        self._validate_package_rules(profile_rules, profile_path)
        duplicated = set(base) & set(profile)
        if duplicated:
            keys = ", ".join(sorted(duplicated))
            raise TemplateError(
                f"Renovate base and profile duplicate top-level keys: {keys}"
            )
        rendered = base | profile
        if base_rules or profile_rules:
            rendered["packageRules"] = [*base_rules, *profile_rules]
        return (json.dumps(rendered, indent=2, ensure_ascii=False) + "\n").encode()

    @staticmethod
    def _load_json_object(path: Path, label: str) -> dict[str, object]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TemplateError(f"cannot load {label} {path}: {error}") from error
        if not isinstance(value, dict):
            raise TemplateError(f"{label} must be a JSON object: {path}")
        return value

    @staticmethod
    def _validate_package_rules(rules: object, path: Path) -> None:
        if not isinstance(rules, list) or not all(
            isinstance(rule, dict) for rule in rules
        ):
            raise TemplateError(f"packageRules must be an array of objects: {path}")

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
        enabled_capabilities: frozenset[str],
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.kind == "static":
            self._copy_static(source.source_path, source.output_path, destination)
            return

        bindings = profile.slots.get(source.output_path, {})
        rendered = self._render_layout(
            profile.name,
            source.source_path,
            bindings,
            overlay_root,
            enabled_capabilities,
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
        bindings: dict[str, SlotBinding],
        overlay_root: Path,
        enabled_capabilities: frozenset[str],
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
            binding = bindings.get(name)
            if (
                binding is not None
                and binding.capability is not None
                and binding.default_fragments is None
                and not optional
            ):
                raise TemplateError(
                    f"capability-owned binding {name!r} in {layout_path} requires an optional slot"
                )
            if binding is not None:
                for branch in (binding.fragments, binding.default_fragments or ()):
                    for reference in branch:
                        self._render_fragment(reference, overlay_root)
            fragments = (
                binding.select(enabled_capabilities) if binding is not None else ()
            )
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
