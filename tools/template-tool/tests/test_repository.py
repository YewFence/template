from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import tomllib
from pathlib import Path

import pytest

from template_tool import TemplateError, TemplateRepository
from template_tool.application import prepare_template


class TestTemplateRepository:
    def setup_method(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.output_directory = tempfile.TemporaryDirectory()
        self.output_root = Path(self.output_directory.name)
        (self.root / "shared/static").mkdir(parents=True)
        (self.root / "overlays/example/static").mkdir(parents=True)

    def teardown_method(self) -> None:
        self.output_directory.cleanup()
        self.temporary_directory.cleanup()

    def write_config(self, body: str = "") -> None:
        (self.root / "templates.toml").write_text(
            "version = 2\n[templates.example]\n"
            "[templates.example.capabilities]\n"
            + body
            + "[templates.example.instantiation]\n"
            'required = ["project_name"]\n'
            "[templates.example.instantiation.tokens]\n"
            'PROJECT_NAME = "project_name"\n'
            "[templates.example.instantiation.validation.metadata]\n"
            'project_name = "Example Project"\n'
            "[templates.example.instantiation.export.metadata]\n"
            'project_name = "REPLACE ME: project name"\n',
            encoding="utf-8",
        )

    def test_static_sources_merge_and_check_detects_changes(self) -> None:
        self.write_config()
        (self.root / "shared/static/LICENSE").write_bytes(b"license\n")
        script = self.root / "overlays/example/static/run"
        script.write_bytes(b"#!/bin/sh\n")
        script.chmod(0o755)

        repository = TemplateRepository(self.root)
        repository.render("example")

        output = self.root / "templates/example"
        assert (stat.S_IMODE(output.stat().st_mode)) == (0o755)
        assert ((output / "LICENSE").read_bytes()) == (b"license\n")
        assert (output / "run").stat().st_mode & stat.S_IXUSR
        assert repository.check("example").matches

        (output / "LICENSE").write_bytes(b"changed\n")
        result = repository.check("example")
        assert not (result.matches)
        assert any("LICENSE" in difference for difference in result.differences)

    def test_capability_outputs_filter_exact_paths_and_directory_prefixes(self) -> None:
        self.write_config(
            "docs-site = true\n"
            "[templates.example.capability_outputs]\n"
            'docs-site = ["docs/", "docs.yml"]\n'
        )
        (self.root / "shared/static/docs").mkdir()
        (self.root / "shared/static/docs/index.md").write_text(
            "documentation\n", encoding="utf-8"
        )
        (self.root / "shared/static/docs.yml").write_text(
            "workflow\n", encoding="utf-8"
        )
        (self.root / "shared/static/README.md").write_text(
            "readme\n", encoding="utf-8"
        )

        repository = TemplateRepository(self.root)
        repository.render("example")
        default_output = self.root / "templates/example"
        assert (default_output / "docs/index.md").is_file()
        assert (default_output / "docs.yml").is_file()

        custom_output = self.output_root / "custom"
        repository.render_to(
            "example",
            custom_output,
            enabled_capabilities=repository.resolve_capabilities(
                "example", disable=("docs-site",)
            ),
        )

        assert ((custom_output / "README.md").read_text()) == ("readme\n")
        assert not ((custom_output / "docs").exists())
        assert not ((custom_output / "docs.yml").exists())
        assert (default_output / "docs/index.md").is_file()

    def test_check_ignores_only_gitignored_extra_paths(self) -> None:
        self.write_config()
        (self.root / "shared/static/.gitignore").write_text(
            "cache/\n", encoding="utf-8"
        )
        (self.root / "shared/static/tracked").write_text("tracked", encoding="utf-8")
        repository = TemplateRepository(self.root)
        repository.render("example")

        output = self.root / "templates/example"
        (output / "cache").mkdir()
        (output / "cache/artifact").write_text("cache", encoding="utf-8")
        assert repository.check("example").matches

        (output / "unexpected").write_text("unexpected", encoding="utf-8")
        result = repository.check("example")
        assert not (result.matches)
        assert ("unexpected path: unexpected") in (result.differences)

    def test_path_rules_only_resolve_real_conflicts_or_omit(self) -> None:
        (self.root / "shared/static/shared-only").write_text("shared", encoding="utf-8")
        (self.root / "shared/static/conflict").write_text("shared", encoding="utf-8")
        (self.root / "overlays/example/static/conflict").write_text(
            "overlay", encoding="utf-8"
        )
        self.write_config(
            '[templates.example.paths]\nconflict = "overlay"\nshared-only = "omit"\n'
        )

        repository = TemplateRepository(self.root)
        repository.render("example")
        output = self.root / "templates/example"
        assert ((output / "conflict").read_text()) == ("overlay")
        assert not ((output / "shared-only").exists())

        self.write_config(
            '[templates.example.paths]\n'
            'conflict = "overlay"\n'
            'shared-only = "shared"\n'
        )
        with pytest.raises(TemplateError, match="redundant"):
            TemplateRepository(self.root).render("example")

    def test_unresolved_cross_owner_conflict_fails(self) -> None:
        self.write_config()
        (self.root / "shared/static/conflict").write_text("shared", encoding="utf-8")
        (self.root / "overlays/example/static/conflict").write_text(
            "overlay", encoding="utf-8"
        )
        with pytest.raises(TemplateError, match="unresolved"):
            TemplateRepository(self.root).render("example")

    def test_layout_renders_bound_fragments_with_custom_delimiters(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/fragments/tasks").mkdir(parents=True)
        (self.root / "shared/layouts/ci.yml.j2").write_text(
            "expr: ${{ github.ref }}\n<$ slot(\"steps\") $>", encoding="utf-8"
        )
        (self.root / "shared/fragments/tasks/check.yml.j2").write_text(
            "- run: mise run check\n", encoding="utf-8"
        )
        self.write_config(
            '[templates.example.slots."ci.yml"]\n'
            'steps = ["shared:tasks/check.yml.j2"]\n'
        )

        TemplateRepository(self.root).render("example")
        assert ((self.root / "templates/example/ci.yml").read_text()) == ("expr: ${{ github.ref }}\n- run: mise run check\n")

    def test_layout_rejects_multiple_consecutive_blank_lines(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/layouts/README.md.j2").write_text(
            "first section\n \n\t\nsecond section\n", encoding="utf-8"
        )
        self.write_config()

        with pytest.raises(TemplateError, match=r"more than one consecutive blank line at output line 2: .*README\.md\.j2"):
            TemplateRepository(self.root).render("example")

    def test_layout_allows_one_blank_line(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/layouts/README.md.j2").write_text(
            "first section\n\nsecond section\n", encoding="utf-8"
        )
        self.write_config()

        TemplateRepository(self.root).render("example")

        assert ((self.root / "templates/example/README.md").read_text()) == ("first section\n\nsecond section\n")

    def test_layout_rejects_multiple_leading_blank_lines(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/layouts/README.md.j2").write_text(
            "\n\nfirst section\n", encoding="utf-8"
        )
        self.write_config()

        with pytest.raises(TemplateError, match=r"more than one consecutive blank line at output line 2: .*README\.md\.j2"):
            TemplateRepository(self.root).render("example")

    def test_conditional_slot_binding_is_omitted_when_capability_is_disabled(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/fragments/tasks").mkdir(parents=True)
        (self.root / "shared/layouts/ci.yml.j2").write_text(
            "steps:\n<$ slot(\"package\", optional=true) $>", encoding="utf-8"
        )
        (self.root / "shared/fragments/tasks/package.yml.j2").write_text(
            "- run: package\n", encoding="utf-8"
        )
        self.write_config(
            "release = false\n"
            '[templates.example.slots."ci.yml"]\n'
            'package = { capability = "release", '
            'fragments = ["shared:tasks/package.yml.j2"] }\n'
        )

        repository = TemplateRepository(self.root)
        repository.render_to(
            "example", self.output_root / "disabled", enabled_capabilities=()
        )
        repository.render_to(
            "example",
            self.output_root / "enabled",
            enabled_capabilities=("release",),
        )

        assert ((self.output_root / "disabled/ci.yml").read_text()) == ("steps:\n")
        assert ((self.output_root / "enabled/ci.yml").read_text()) == ("steps:\n- run: package\n")

    def test_variant_slot_binding_replaces_default_fragments(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/fragments/package").mkdir(parents=True)
        (self.root / "shared/layouts/Cargo.toml.j2").write_text(
            "[package]\n<$ slot(\"publish\") $>", encoding="utf-8"
        )
        (self.root / "shared/fragments/package/disabled.toml.j2").write_text(
            "publish = false\n", encoding="utf-8"
        )
        (self.root / "shared/fragments/package/crates-io.toml.j2").write_text(
            'publish = ["crates-io"]\n', encoding="utf-8"
        )
        self.write_config(
            "crates-io-publish = false\n"
            '[templates.example.slots."Cargo.toml"]\n'
            'publish = { capability = "crates-io-publish", '
            'default_fragments = ["shared:package/disabled.toml.j2"], '
            'fragments = ["shared:package/crates-io.toml.j2"] }\n'
        )

        repository = TemplateRepository(self.root)
        repository.render_to(
            "example", self.output_root / "disabled", enabled_capabilities=()
        )
        repository.render_to(
            "example",
            self.output_root / "enabled",
            enabled_capabilities=("crates-io-publish",),
        )

        assert ((self.output_root / "disabled/Cargo.toml").read_text()) == ("[package]\npublish = false\n")
        assert ((self.output_root / "enabled/Cargo.toml").read_text()) == ('[package]\npublish = ["crates-io"]\n')

    def test_capability_output_selectors_must_be_disjoint_and_match_sources(self) -> None:
        (self.root / "shared/static/docs").mkdir()
        (self.root / "shared/static/docs/index.md").write_text(
            "documentation\n", encoding="utf-8"
        )
        cases = (
            (
                'docs-site = ["docs/", "docs/index.md"]\n',
                "matched by multiple capability output selectors",
            ),
            ('docs-site = ["missing/"]\n', "does not match any output"),
            ('docs-site = ["docs/*.md"]\n', "must not use glob syntax"),
        )
        for declaration, message in cases:
            self.write_config(
                "docs-site = true\n"
                "[templates.example.capability_outputs]\n"
                + declaration
            )
            with pytest.raises(TemplateError, match=message):
                TemplateRepository(self.root).render("example")

    def test_conditional_binding_requires_optional_slot(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/fragments/tasks").mkdir(parents=True)
        (self.root / "shared/layouts/ci.yml.j2").write_text(
            "<$ slot(\"package\") $>", encoding="utf-8"
        )
        (self.root / "shared/fragments/tasks/package.yml.j2").write_text(
            "- run: package\n", encoding="utf-8"
        )
        self.write_config(
            "release = false\n"
            '[templates.example.slots."ci.yml"]\n'
            'package = { capability = "release", '
            'fragments = ["shared:tasks/package.yml.j2"] }\n'
        )

        with pytest.raises(TemplateError, match="requires an optional slot"):
            TemplateRepository(self.root).render("example")

    def test_every_capability_must_affect_an_output_or_slot_binding(self) -> None:
        self.write_config("unused = false\n")

        with pytest.raises(TemplateError, match="capability has no delivery effect.*unused"):
            TemplateRepository(self.root).render("example")

    def test_capability_ownership_rejects_undeclared_capabilities(self) -> None:
        cases = (
            (
                "[templates.example.capability_outputs]\n"
                'unknown = ["README.md"]\n',
                "capability_outputs references undeclared capability",
            ),
            (
                '[templates.example.slots."ci.yml"]\n'
                'steps = { capability = "unknown", '
                'fragments = ["shared:tasks/check.yml.j2"] }\n',
                "binding example:ci.yml:steps references undeclared capability",
            ),
        )
        for body, message in cases:
            self.write_config(body)
            with pytest.raises(TemplateError, match=message):
                TemplateRepository(self.root)

    def test_capability_bindings_require_non_empty_fragment_groups(self) -> None:
        cases = (
            ('fragments = []', "fragments must be a non-empty array"),
            (
                'fragments = ["shared:tasks/check.yml.j2"], '
                "default_fragments = []",
                "default_fragments must be a non-empty array",
            ),
        )
        for declaration, message in cases:
            self.write_config(
                "release = false\n"
                '[templates.example.slots."ci.yml"]\n'
                'steps = { capability = "release", '
                + declaration
                + " }\n"
            )
            with pytest.raises(TemplateError, match=message):
                TemplateRepository(self.root)

    def test_render_and_check_use_only_default_capability_set(self) -> None:
        self.write_config(
            "release = false\n"
            "[templates.example.capability_outputs]\n"
            'release = ["release.yml"]\n'
        )
        (self.root / "shared/static/README.md").write_text(
            "readme\n", encoding="utf-8"
        )
        (self.root / "shared/static/release.yml").write_text(
            "release\n", encoding="utf-8"
        )

        repository = TemplateRepository(self.root)
        repository.render("example")
        snapshot = self.root / "templates/example"
        assert not ((snapshot / "release.yml").exists())
        assert repository.check("example").matches

        repository.render_to(
            "example",
            self.output_root / "enabled",
            enabled_capabilities=("release",),
        )
        assert (self.output_root / "enabled/release.yml").is_file()
        assert not ((snapshot / "release.yml").exists())
        assert repository.check("example").matches

    def test_directory_selector_does_not_match_same_named_file(self) -> None:
        self.write_config(
            "docs-site = true\n"
            "[templates.example.capability_outputs]\n"
            'docs-site = ["docs/"]\n'
        )
        (self.root / "shared/static/docs").write_text("file\n", encoding="utf-8")

        with pytest.raises(TemplateError, match="does not match any output"):
            TemplateRepository(self.root).render("example")

    def test_capability_output_rejects_cross_capability_selector_overlap(self) -> None:
        self.write_config(
            "docs-site = true\n"
            "release = false\n"
            "[templates.example.capability_outputs]\n"
            'docs-site = ["docs/"]\n'
            'release = ["docs/index.md"]\n'
        )
        (self.root / "shared/static/docs").mkdir()
        (self.root / "shared/static/docs/index.md").write_text(
            "documentation\n", encoding="utf-8"
        )

        with pytest.raises(TemplateError, match="matched by multiple capability output selectors"):
            TemplateRepository(self.root).render("example")

    def test_inactive_fragment_branches_are_still_validated(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/fragments/package").mkdir(parents=True)
        (self.root / "shared/layouts/Cargo.toml.j2").write_text(
            "<$ slot(\"publish\") $>", encoding="utf-8"
        )
        (self.root / "shared/fragments/package/disabled.toml.j2").write_text(
            "publish = false\n", encoding="utf-8"
        )
        cases = (
            (
                'default_fragments = ["shared:package/disabled.toml.j2"], '
                'fragments = ["overlay:missing.toml.j2"]',
                (),
            ),
            (
                'default_fragments = ["overlay:missing.toml.j2"], '
                'fragments = ["shared:package/disabled.toml.j2"]',
                ("release",),
            ),
        )
        for declaration, enabled in cases:
            self.write_config(
                "release = false\n"
                '[templates.example.slots."Cargo.toml"]\n'
                'publish = { capability = "release", '
                + declaration
                + " }\n"
            )
            repository = TemplateRepository(self.root)
            with pytest.raises(TemplateError, match="invalid fragment reference"):
                repository.render_to(
                    "example",
                    self.output_root / "output",
                    enabled_capabilities=enabled,
                )

    def test_disabled_owned_layout_still_validates_required_slots(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/layouts/docs.yml.j2").write_text(
            "<$ slot(\"steps\") $>", encoding="utf-8"
        )
        self.write_config(
            "docs-site = false\n"
            "[templates.example.capability_outputs]\n"
            'docs-site = ["docs.yml"]\n'
        )

        repository = TemplateRepository(self.root)
        with pytest.raises(TemplateError, match="does not bind required slot"):
            repository.render_to(
                "example", self.output_root / "disabled", enabled_capabilities=()
            )

    def test_disabled_owned_static_symlink_is_still_validated(self) -> None:
        self.write_config(
            "docs-site = false\n"
            "[templates.example.capability_outputs]\n"
            'docs-site = ["docs-link"]\n'
        )
        os.symlink("../outside", self.root / "shared/static/docs-link")

        repository = TemplateRepository(self.root)
        with pytest.raises(TemplateError, match="symlink escapes"):
            repository.render_to(
                "example", self.output_root / "disabled", enabled_capabilities=()
            )

    def test_render_to_rejects_repository_owned_destinations(self) -> None:
        self.write_config()
        repository = TemplateRepository(self.root)
        ancestor_marker = self.root.parent / "ancestor-marker"
        ancestor_marker.write_text("keep\n", encoding="utf-8")

        for destination in (
            self.root.parent,
            self.root,
            self.root / "templates/example",
            self.root / "shared/generated",
            self.root / "overlays/example/generated",
            self.root / "config/generated",
            self.root / "tools/generated",
        ):
            with pytest.raises(TemplateError, match="destination must be outside repository-owned paths"):
                repository.render_to(
                    "example", destination, enabled_capabilities=()
                )
        assert (ancestor_marker.read_text()) == ("keep\n")
        ancestor_marker.unlink()

    def test_static_symlink_must_stay_inside_template(self) -> None:
        self.write_config()
        os.symlink("../outside", self.root / "shared/static/link")
        with pytest.raises(TemplateError, match="escapes"):
            TemplateRepository(self.root).render("example")

    def test_instantiation_profile_requires_valid_validation_metadata(self) -> None:
        (self.root / "templates.toml").write_text(
            "version = 2\n"
            "[templates.example.capabilities]\n"
            "[templates.example.instantiation]\n"
            'required = ["project_name"]\n'
            "[templates.example.instantiation.tokens]\n"
            'PROJECT_NAME = "project_name"\n'
            "[templates.example.instantiation.validation.metadata]\n"
            "[templates.example.instantiation.export.metadata]\n"
            'project_name = "REPLACE ME: project name"\n',
            encoding="utf-8",
        )
        with pytest.raises(TemplateError, match="missing required metadata"):
            TemplateRepository(self.root)

    def test_instantiation_profile_requires_complete_export_metadata(self) -> None:
        self.write_config()
        config = (self.root / "templates.toml").read_text(encoding="utf-8")
        (self.root / "templates.toml").write_text(
            config.replace('project_name = "REPLACE ME: project name"\n', ""),
            encoding="utf-8",
        )

        with pytest.raises(TemplateError, match="invalid export metadata"):
            TemplateRepository(self.root)

    def test_renovate_module_generates_root_and_template_configs(self) -> None:
        self.write_config()
        (self.root / "shared/renovate").mkdir(parents=True)
        (self.root / "config/renovate").mkdir(parents=True)
        (self.root / "overlays/example/fragments/renovate").mkdir(parents=True)
        (self.root / "shared/renovate/base.json").write_text(
            json.dumps(
                {
                    "timezone": "Asia/Shanghai",
                    "packageRules": [{"description": "base"}],
                }
            ),
            encoding="utf-8",
        )
        (self.root / "config/renovate/monorepo.json").write_text(
            json.dumps(
                {
                    "enabledManagers": ["mise"],
                    "ignorePaths": ["templates/**"],
                    "packageRules": [{"description": "root"}],
                }
            ),
            encoding="utf-8",
        )
        (self.root / "overlays/example/fragments/renovate/profile.json").write_text(
            json.dumps(
                {
                    "enabledManagers": ["npm"],
                    "packageRules": [{"description": "template"}],
                }
            ),
            encoding="utf-8",
        )

        repository = TemplateRepository(self.root)
        repository.render_repository()
        repository.render("example")

        root_config = json.loads((self.root / "renovate.json").read_text())
        template_config = json.loads(
            (self.root / "templates/example/renovate.json").read_text()
        )
        assert (root_config["ignorePaths"]) == (["templates/**"])
        assert ([rule["description"] for rule in root_config["packageRules"]]) == (["base", "root"])
        assert (template_config["enabledManagers"]) == (["npm"])
        assert ([rule["description"] for rule in template_config["packageRules"]]) == (["base", "template"])
        assert repository.check_repository().matches
        assert repository.check("example").matches

    def test_renovate_module_rejects_duplicate_top_level_ownership(self) -> None:
        self.write_config()
        (self.root / "shared/renovate").mkdir(parents=True)
        (self.root / "overlays/example/fragments/renovate").mkdir(parents=True)
        (self.root / "shared/renovate/base.json").write_text(
            '{"enabledManagers": ["mise"]}', encoding="utf-8"
        )
        (self.root / "overlays/example/fragments/renovate/profile.json").write_text(
            '{"enabledManagers": ["npm"]}', encoding="utf-8"
        )

        with pytest.raises(TemplateError, match="duplicate top-level keys"):
            TemplateRepository(self.root).render("example")

    def test_renovate_capability_contribution_is_filtered_and_validated(self) -> None:
        self.write_config(
            "docs-site = true\n"
            "[templates.example.capability_outputs]\n"
            'docs-site = ["docs/"]\n'
        )
        (self.root / "shared/static/docs").mkdir()
        (self.root / "shared/static/docs/index.md").write_text(
            "documentation\n", encoding="utf-8"
        )
        (self.root / "shared/renovate").mkdir(parents=True)
        (self.root / "overlays/example/fragments/renovate").mkdir(parents=True)
        (self.root / "shared/renovate/base.json").write_text(
            '{"packageRules": []}', encoding="utf-8"
        )
        profile_path = self.root / "overlays/example/fragments/renovate/profile.json"
        profile_path.write_text(
            json.dumps(
                {
                    "enabledManagers": ["mise", "npm"],
                    "capabilityContributions": {
                        "docs-site": {
                            "enabledManagers": ["npm"],
                            "packageRules": [
                                {
                                    "description": "documentation",
                                    "matchManagers": ["npm"],
                                }
                            ],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        repository = TemplateRepository(self.root)
        repository.render_to(
            "example", self.output_root / "disabled", enabled_capabilities=()
        )
        repository.render_to(
            "example",
            self.output_root / "enabled",
            enabled_capabilities=("docs-site",),
        )

        disabled = json.loads(
            (self.output_root / "disabled/renovate.json").read_text()
        )
        enabled = json.loads((self.output_root / "enabled/renovate.json").read_text())
        assert (disabled["enabledManagers"]) == (["mise"])
        assert ("packageRules") not in (disabled)
        assert (enabled["enabledManagers"]) == (["mise", "npm"])
        assert (enabled["packageRules"][0]["description"]) == ("documentation")

        profile_path.write_text(
            json.dumps(
                {
                    "capabilityContributions": {
                        "unknown": {"enabledManagers": ["npm"]}
                    }
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(TemplateError, match="contribution references undeclared capability"):
            TemplateRepository(self.root).render("example")

    @pytest.mark.parametrize("template", ("common", "python", "go-cli", "rust"))
    @pytest.mark.parametrize("task_name", ("newline:check", "newline:fix"))
    def test_newline_tasks_use_bash_and_nul_delimited_paths(
        self, template: str, task_name: str
    ) -> None:
        repository = TemplateRepository(Path(__file__).resolve().parents[3])
        output = self.output_root / template
        repository.render_to(template, output, enabled_capabilities=())
        task = tomllib.loads((output / "mise.toml").read_text())["tasks"][task_name]

        assert task["shell"] == "bash -c"
        assert "set -o pipefail" in task["run"]
        fix_option = "--fix " if task_name == "newline:fix" else ""
        assert (
            'jj --ignore-working-copy file list -T \'path ++ "\\0"\' | '
            f"xargs -0 nllint {fix_option}--trim-space"
        ) in task["run"]
        assert "xargs -d" not in task["run"]

    @pytest.mark.parametrize("template", ("common", "python", "go-cli", "rust"))
    @pytest.mark.parametrize("capabilities_enabled", (False, True))
    def test_release_workflow_uses_shared_gh_adapter(
        self, template: str, capabilities_enabled: bool
    ) -> None:
        repository = TemplateRepository(Path(__file__).resolve().parents[3])
        capabilities = repository.resolve_capabilities(template) if capabilities_enabled else ()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / template
            repository.render_to(template, output, enabled_capabilities=capabilities)
            workflow = (output / ".github/workflows/release.yml").read_text()
            ci_tasks = tomllib.loads((output / "mise.ci.toml").read_text())["tasks"]
            assert (output / ".github/scripts/publish-release.sh").is_file()
            assert "run: bash .github/scripts/publish-release.sh" in workflow
            assert 'checkout_ref="$(git rev-parse HEAD)"' in workflow
            assert 'checkout_ref="${REF_NAME}"' not in workflow
            assert 'checkout_ref="${INPUT_TAG}"' not in workflow
            assert "group: github-release-${{ needs.version.outputs.tag }}" in workflow
            assert "RELEASE_COMMIT: ${{ needs.version.outputs.checkout_ref }}" in workflow
            assert "ALLOW_TAG_CREATION: ${{ needs.version.outputs.allow_tag_creation }}" in workflow
            assert ("RELEASE_ASSET_DIR: dist" in workflow) is (template in {"go-cli", "rust"})
            assert "softprops/action-gh-release" not in workflow
            assert "git push" not in workflow
            assert "release:tag:create" not in ci_tasks
            assert "release:tag" in ci_tasks

    @pytest.mark.parametrize("template", ("common", "python", "go-cli", "rust"))
    @pytest.mark.parametrize("docs_enabled", (False, True))
    def test_action_pins_workflow_is_separate_from_ci(
        self, template: str, docs_enabled: bool
    ) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        repository = TemplateRepository(repository_root)
        capabilities = repository.resolve_capabilities(template)
        if not docs_enabled:
            capabilities = tuple(c for c in capabilities if c != "docs-site")

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / template
            repository.render_to(template, output, enabled_capabilities=capabilities)
            workflow = (output / ".github/workflows/actions-pin.yml").read_text()
            ci = (output / ".github/workflows/ci.yml").read_text()
            mise = (output / "mise.toml").read_text()
            mise_ci = (output / "mise.ci.toml").read_text()

            assert "on:\n  push:\n    branches: [main]\n  workflow_dispatch:\n" in workflow
            assert "if: github.ref == 'refs/heads/main'" in workflow
            assert "pull_request:" not in workflow
            assert "run: mise run actions:pin:check" in workflow
            assert "actions-pin:" not in ci
            assert "actions:pin:check" not in ci
            assert "actions:outdated" not in mise_ci
            assert "actions:versions:check" not in mise_ci
            assert "  pull_request:\n    branches: [main]" in ci
            assert "run: mise run check" in ci
            assert '{ task = "actions:check" }' in mise
            assert 'depends = ["actions:pin-offline:check"]' in mise

    def test_docs_site_capability_renders_complete_profile_variants(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        repository = TemplateRepository(repository_root)

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            for template in ("common", "python", "go-cli", "rust"):
                enabled_capabilities = repository.resolve_capabilities(template)
                disabled_capabilities = tuple(
                    capability
                    for capability in enabled_capabilities
                    if capability != "docs-site"
                )
                enabled = output_root / template / "enabled"
                disabled = output_root / template / "disabled"
                repository.render_to(
                    template,
                    enabled,
                    enabled_capabilities=enabled_capabilities,
                )
                repository.render_to(
                    template,
                    disabled,
                    enabled_capabilities=disabled_capabilities,
                )

                assert (enabled / "docs/package.json").is_file()
                assert (enabled / ".github/workflows/docs.yml").is_file()
                docs_workflow = (enabled / ".github/workflows/docs.yml").read_text()
                assert (
                    'on:\n  push:\n    branches: [main]\n    paths:\n'
                    '      - "docs/**"\n  workflow_dispatch:\n'
                ) in docs_workflow
                assert not ((disabled / "docs").exists())
                assert not ((disabled / ".github/workflows/docs.yml").exists())

                enabled_mise = (enabled / "mise.toml").read_text()
                disabled_mise = (disabled / "mise.toml").read_text()
                assert ('node = "26"') in (enabled_mise)
                assert ('pnpm = "11"') in (enabled_mise)
                assert ("[tasks.'docs:build']") in (enabled_mise)
                assert ('node = "26"') not in (disabled_mise)
                assert ('pnpm = "11"') not in (disabled_mise)
                assert ("docs:build") not in (disabled_mise)

                enabled_ci = (enabled / ".github/workflows/ci.yml").read_text()
                disabled_ci = (disabled / ".github/workflows/ci.yml").read_text()
                assert ("  docs:\n") in (enabled_ci)
                assert ("  docs:\n") not in (disabled_ci)
                assert (enabled_ci) == (enabled_ci.rstrip() + "\n")
                assert (disabled_ci) == (disabled_ci.rstrip() + "\n")
                assert (enabled_mise) == (enabled_mise.rstrip() + "\n")
                assert (disabled_mise) == (disabled_mise.rstrip() + "\n")

                enabled_readme = (enabled / "README.md").read_text()
                disabled_readme = (disabled / "README.md").read_text()
                assert ("docs-online-blue") in (enabled_readme)
                assert ("## Documentation") in (enabled_readme)
                assert ("docs-online-blue") not in (disabled_readme)
                assert ("## Documentation") not in (disabled_readme)

                enabled_contributing = (enabled / "CONTRIBUTING.md").read_text()
                disabled_contributing = (
                    disabled / "CONTRIBUTING.md"
                ).read_text()
                assert ("Documentation Site") in (enabled_contributing)
                assert ("Documentation Site") not in (disabled_contributing)

                enabled_gitignore = (enabled / ".gitignore").read_text()
                disabled_gitignore = (disabled / ".gitignore").read_text()
                assert ("/docs/node_modules/") in (enabled_gitignore)
                assert ("/docs/node_modules/") not in (disabled_gitignore)
                assert not (disabled_gitignore.startswith("\n"))

                enabled_renovate = json.loads(
                    (enabled / "renovate.json").read_text()
                )
                disabled_renovate = json.loads(
                    (disabled / "renovate.json").read_text()
                )
                assert ("npm") in (enabled_renovate["enabledManagers"])
                assert ("npm") not in (disabled_renovate["enabledManagers"])
                assert any(
                        rule.get("matchManagers") == ["npm"]
                        for rule in enabled_renovate["packageRules"]
                    )
                assert not (any(
                        rule.get("matchManagers") == ["npm"]
                        for rule in disabled_renovate["packageRules"]
                    ))

    def test_codecov_upload_capability_renders_complete_profile_variants(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        repository = TemplateRepository(repository_root)
        reports = {
            "common": "coverage.xml",
            "python": "coverage.xml",
            "go-cli": "coverage.out",
            "rust": "lcov.info",
        }

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            for template, report in reports.items():
                disabled = output_root / template / "disabled"
                enabled = output_root / template / "enabled"
                repository.render_to(template, disabled, enabled_capabilities=())
                repository.render_to(
                    template,
                    enabled,
                    enabled_capabilities=("codecov-upload",),
                )

                disabled_ci = (disabled / ".github/workflows/ci.yml").read_text()
                disabled_mise = (disabled / "mise.toml").read_text()
                disabled_ci_mise = (disabled / "mise.ci.toml").read_text()
                assert ("  coverage:\n") not in (disabled_ci)
                assert ("[tasks.coverage]") not in (disabled_mise)
                assert ("codecov-cli") not in (disabled_ci_mise)
                assert (f"/{report}") not in ((disabled / ".gitignore").read_text())
                assert not ((disabled / ".github/workflows/coverage.yml").exists())

                enabled_ci = (enabled / ".github/workflows/ci.yml").read_text()
                coverage = (
                    enabled / ".github/workflows/coverage.yml"
                ).read_text()
                enabled_mise = (enabled / "mise.toml").read_text()
                enabled_ci_mise = (enabled / "mise.ci.toml").read_text()
                assert ("  coverage:\n") in (enabled_ci)
                assert ("if: ${{ github.event_name == 'pull_request' }}") in (enabled_ci)
                assert ("    contents: read\n") in (enabled_ci)
                assert ("id-token: write") not in (enabled_ci)
                assert ("use_oidc:") not in (enabled_ci)
                assert ("push:\n    branches: [main]") in (coverage)
                assert ("workflow_dispatch:") in (coverage)
                assert ("github.event_name == 'push' || github.ref == 'refs/heads/main'") in (coverage)
                assert ("id-token: write") in (coverage)
                assert ("group: coverage-${{ github.ref }}") in (coverage)
                assert ("cancel-in-progress: true") in (coverage)
                assert ("use_oidc: true") in (coverage)

                for workflow in (enabled_ci, coverage):
                    assert ("uses: codecov/codecov-action@v7") in (workflow)
                    assert ("binary: ${{ steps.codecov-cli.outputs.path }}") in (workflow)
                    assert ("files: ${{ steps.coverage.outputs.report }}") in (workflow)
                    assert ("disable_search: true") in (workflow)
                    assert ("fail_ci_if_error: true") in (workflow)
                    assert ("mise which codecovcli") in (workflow)
                    assert ("CODECOV_TOKEN") not in (workflow)
                    assert ("override_branch") not in (workflow)
                    assert ("override_pr") not in (workflow)
                    assert ("skip_validation") not in (workflow)

                assert ("[tasks.coverage]") in (enabled_mise)
                assert (f"/{report}") in ((enabled / ".gitignore").read_text())
                assert ('"pipx:codecov-cli" = "11"') in (enabled_ci_mise)
                if template == "rust":
                    assert ('"cargo:cargo-llvm-cov" = "0.8"') in (enabled_ci_mise)
                else:
                    assert ("cargo-llvm-cov") not in (enabled_ci_mise)

    def test_export_metadata_instantiates_every_profile_and_derived_value(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        repository = TemplateRepository(repository_root)

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            for template in ("common", "python", "go-cli", "rust"):
                metadata = repository.export_metadata(template)
                if template == "rust":
                    metadata["description"] = 'Replace "this" description'
                output = output_root / template
                prepare_template(
                    repository,
                    template,
                    output,
                    metadata=metadata,
                )

                for path in output.rglob("*"):
                    assert not re.search(r"\{\{[A-Z]", str(path.relative_to(output)))
                    if path.is_file():
                        try:
                            content = path.read_text(encoding="utf-8")
                        except UnicodeDecodeError:
                            continue
                        assert not re.search(r"\{\{[A-Z]", content)

                if template == "python":
                    assert (output / "src/replace_me_package/__init__.py").is_file()
                    pyproject = (output / "pyproject.toml").read_text(encoding="utf-8")
                    assert 'packages = ["src/replace_me_package"]' in pyproject
                if template == "go-cli":
                    assert (output / "cmd/replace-me-binary/main.go").is_file()
                    assert ((output / "go.mod").read_text(encoding="utf-8").splitlines()[0]) == ("module example.invalid/replace-me-module")
                if template == "rust":
                    cargo = (output / "Cargo.toml").read_text(encoding="utf-8")
                    main = (output / "src/main.rs").read_text(encoding="utf-8")
                    docs = (output / "docs/index.md").read_text(encoding="utf-8")
                    assert ('description = "Replace \\"this\\" description"') in (cargo)
                    assert ("replace_me_package::greeting") in (main)
                    assert ('text: "Replace \\"this\\" description"') in (docs)

    def test_python_profile_renders_language_toolchain_and_package(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        repository = TemplateRepository(repository_root)
        metadata = repository.validation_metadata("python")

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            disabled = output_root / "disabled"
            enabled = output_root / "enabled"
            repository.render_to("python", disabled, enabled_capabilities=())
            repository.render_to(
                "python",
                enabled,
                enabled_capabilities=("codecov-upload",),
            )
            repository.instantiate("python", disabled, metadata)
            repository.instantiate("python", enabled, metadata)

            mise = tomllib.loads((disabled / "mise.toml").read_text())
            assert mise["tools"]["python"] == "3"
            assert mise["tools"]["uv"] == "0"
            assert mise["tools"]["ruff"] == "0.16"
            assert mise["tools"]["ty"] == "0.0"
            assert mise["tasks"]["lint"]["run"] == ["ruff check .", "ty check"]

            pyproject = tomllib.loads((disabled / "pyproject.toml").read_text())
            assert pyproject["project"]["name"] == "example-python-project"
            assert pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
                "src/example_python_project"
            ]
            assert "coverage" not in pyproject["dependency-groups"]
            assert (disabled / "src/example_python_project/__init__.py").is_file()
            assert (disabled / "tests/test_package.py").is_file()

            enabled_pyproject = tomllib.loads((enabled / "pyproject.toml").read_text())
            assert enabled_pyproject["dependency-groups"]["coverage"] == [
                "pytest-cov>=7,<8"
            ]
            assert "--cov=example_python_project" in (
                enabled / "mise.toml"
            ).read_text()

    def test_rust_crates_io_publish_capability_renders_complete_variants(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        repository = TemplateRepository(repository_root)
        metadata = repository.validation_metadata("rust") | {
            "description": 'Example "Rust" CLI description',
        }

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            disabled = output_root / "disabled"
            enabled = output_root / "enabled"
            repository.render_to(
                "rust",
                disabled,
                enabled_capabilities=(),
            )
            repository.render_to(
                "rust",
                enabled,
                enabled_capabilities=("crates-io-publish",),
            )
            repository.instantiate("rust", disabled, metadata)
            repository.instantiate("rust", enabled, metadata)

            disabled_cargo = tomllib.loads((disabled / "Cargo.toml").read_text())
            enabled_cargo = tomllib.loads((enabled / "Cargo.toml").read_text())
            assert (disabled_cargo["package"]["publish"]) == (False)
            assert (enabled_cargo["package"]["publish"]) == (["crates-io"])
            assert (enabled_cargo["package"]["description"]) == ('Example "Rust" CLI description')
            assert (enabled_cargo["package"]["license"]) == ("MIT")
            assert (enabled_cargo["package"]["repository"]) == ("https://github.com/YewFence/example-rust-cli")
            assert (enabled_cargo["package"]["readme"]) == ("README.md")

            disabled_mise = (disabled / "mise.ci.toml").read_text()
            enabled_mise = (enabled / "mise.ci.toml").read_text()
            assert ("crates-io:package:check") not in (disabled_mise)
            assert ("crates-io:publish") not in (disabled_mise)
            assert ('jq = "1"') not in (disabled_mise)
            assert ('[tasks."crates-io:package:check"]') in (enabled_mise)
            assert ('run = "cargo package --locked"') in (enabled_mise)
            assert ('[tasks."crates-io:publish"]') in (enabled_mise)
            assert ('file = "scripts/publish-crate"') in (enabled_mise)
            assert ('jq = "1"') in (enabled_mise)

            disabled_publish_script = disabled / "scripts/publish-crate"
            publish_script = enabled / "scripts/publish-crate"
            assert not (disabled_publish_script.exists())
            assert publish_script.stat().st_mode & stat.S_IXUSR
            publish_script_text = publish_script.read_text()
            assert ("cargo metadata --locked --no-deps --format-version 1") in (publish_script_text)
            assert ("--user-agent \"${crate_name}-publish "
                "(https://github.com/YewFence/example-rust-cli)\"") in (publish_script_text)
            assert ("https://crates.io/api/v1/crates/") in (publish_script_text)
            assert ("cargo publish --dry-run") in (publish_script_text)
            assert ("crates.io trusted publishing did not provide a token") in (publish_script_text)

            disabled_ci = (disabled / ".github/workflows/ci.yml").read_text()
            enabled_ci = (enabled / ".github/workflows/ci.yml").read_text()
            assert ("crates-io:package:check") not in (disabled_ci)
            assert ("mise run crates-io:package:check") in (enabled_ci)
            assert ("github.event_name == 'pull_request'") in (enabled_ci)

            assert not ((disabled / "CRATES_IO_PUBLISHING.md").exists())
            assert not ((enabled / "CRATES_IO_PUBLISHING.md").exists())

            release = (enabled / ".github/workflows/release.yml").read_text()
            disabled_release = (disabled / ".github/workflows/release.yml").read_text()
            assert ("matrix.packages") not in (release)
            assert ("  publish-crate:\n") not in (disabled_release)
            assert ("  publish-crate:\n") in (release)
            assert ("needs: [version, build, release]") in (release)
            assert ("cargo metadata") not in (release)
            assert ("https://crates.io/api/v1/crates/") not in (release)
            assert ("cargo publish") not in (release)
            assert ("continue-on-error: true") in (release)
            assert ("rust-lang/crates-io-auth-action@v1") in (release)
            assert ("run: mise run crates-io:publish") in (release)
            assert (release.index("  publish-crate:\n")) < (release.index("  close-superseded-release-pr:\n"))
            assert (release.index("uses: rust-lang/crates-io-auth-action@v1")) < (release.index("run: mise run crates-io:publish"))

    def test_go_cli_container_image_publish_capability_renders_complete_variants(
        self,
    ) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        repository = TemplateRepository(repository_root)
        metadata = repository.validation_metadata("go-cli")

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            disabled = output_root / "disabled"
            enabled = output_root / "enabled"
            repository.render_to("go-cli", disabled, enabled_capabilities=())
            repository.render_to(
                "go-cli",
                enabled,
                enabled_capabilities=("container-image-publish",),
            )
            repository.instantiate("go-cli", disabled, metadata)
            repository.instantiate("go-cli", enabled, metadata)

            disabled_mise = (disabled / "mise.ci.toml").read_text()
            enabled_mise = (enabled / "mise.ci.toml").read_text()
            assert ("container:build") not in (disabled_mise)
            assert ("container:publish") not in (disabled_mise)
            assert ("aqua:ko-build/ko") not in (disabled_mise)
            assert ('"aqua:ko-build/ko" = "0.19"') in (enabled_mise)
            assert ('[tasks."container:build"]') in (enabled_mise)
            assert ("ko build --local --tags dev") in (enabled_mise)
            assert ('CONTAINER_IMAGE_REPOSITORY:-ko.local') in (enabled_mise)
            assert ("CONTAINER_IMAGE_REPOSITORY must be a complete registry/repository name") in (enabled_mise)
            assert ('CONTAINER_IMAGE_PLATFORM:-') in (enabled_mise)
            assert ('[tasks."container:publish"]') in (enabled_mise)
            assert ("--bare --platform=all") in (enabled_mise)
            assert ("tag_args+=(--tags latest)") in (enabled_mise)
            assert ("ghcr.io/YewFence/example-go-cli") in (enabled_mise)
            assert ("./cmd/example-go-cli") in (enabled_mise)
            assert ("./cmd/your-cli") not in (enabled_mise)

            disabled_release = (
                disabled / ".github/workflows/release.yml"
            ).read_text()
            release = (enabled / ".github/workflows/release.yml").read_text()
            assert ("  publish-container:\n") not in (disabled_release)
            assert ("packages: write") not in (disabled_release)
            assert ("ko login ghcr.io") not in (disabled_release)
            assert ("  publish-container:\n") in (release)
            assert ("needs: [version, release]") in (release)
            assert ("packages: write") in (release)
            assert ("ko login ghcr.io") in (release)
            assert ("CONTAINER_IMAGE_REPOSITORY: ghcr.io/YewFence/example-go-cli") in (release)
            assert ("RELEASE_PRERELEASE: ${{ needs.version.outputs.prerelease }}") in (release)
            assert ("run: mise run container:publish") in (release)
            assert ("ko build") not in (release)
            assert (release.index("  release:\n")) < (release.index("  publish-container:\n"))
            assert (release.index("ko login ghcr.io")) < (release.index("run: mise run container:publish"))

            disabled_readme = (disabled / "README.md").read_text()
            enabled_readme = (enabled / "README.md").read_text()
            assert ("## Container Image") not in (disabled_readme)
            assert ("## Container Image") in (enabled_readme)
            assert ("ghcr.io/YewFence/example-go-cli:vMAJOR.MINOR.PATCH") in (enabled_readme)

            for output in ("Dockerfile", "ko.yaml", ".ko.yaml"):
                assert not ((enabled / output).exists())
