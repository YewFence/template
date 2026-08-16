from __future__ import annotations

import json
import os
import stat
import tempfile
import tomllib
import unittest
from pathlib import Path

from template_tool import TemplateError, TemplateRepository
from template_tool.application import prepare_template


class TemplateRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.output_directory = tempfile.TemporaryDirectory()
        self.output_root = Path(self.output_directory.name)
        (self.root / "shared/static").mkdir(parents=True)
        (self.root / "overlays/example/static").mkdir(parents=True)

    def tearDown(self) -> None:
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
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o755)
        self.assertEqual((output / "LICENSE").read_bytes(), b"license\n")
        self.assertTrue((output / "run").stat().st_mode & stat.S_IXUSR)
        self.assertTrue(repository.check("example").matches)

        (output / "LICENSE").write_bytes(b"changed\n")
        result = repository.check("example")
        self.assertFalse(result.matches)
        self.assertTrue(any("LICENSE" in difference for difference in result.differences))

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
        self.assertTrue((default_output / "docs/index.md").is_file())
        self.assertTrue((default_output / "docs.yml").is_file())

        custom_output = self.output_root / "custom"
        repository.render_to(
            "example",
            custom_output,
            enabled_capabilities=repository.resolve_capabilities(
                "example", disable=("docs-site",)
            ),
        )

        self.assertEqual((custom_output / "README.md").read_text(), "readme\n")
        self.assertFalse((custom_output / "docs").exists())
        self.assertFalse((custom_output / "docs.yml").exists())
        self.assertTrue((default_output / "docs/index.md").is_file())

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
        self.assertTrue(repository.check("example").matches)

        (output / "unexpected").write_text("unexpected", encoding="utf-8")
        result = repository.check("example")
        self.assertFalse(result.matches)
        self.assertIn("unexpected path: unexpected", result.differences)

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
        self.assertEqual((output / "conflict").read_text(), "overlay")
        self.assertFalse((output / "shared-only").exists())

        self.write_config(
            '[templates.example.paths]\n'
            'conflict = "overlay"\n'
            'shared-only = "shared"\n'
        )
        with self.assertRaisesRegex(TemplateError, "redundant"):
            TemplateRepository(self.root).render("example")

    def test_unresolved_cross_owner_conflict_fails(self) -> None:
        self.write_config()
        (self.root / "shared/static/conflict").write_text("shared", encoding="utf-8")
        (self.root / "overlays/example/static/conflict").write_text(
            "overlay", encoding="utf-8"
        )
        with self.assertRaisesRegex(TemplateError, "unresolved"):
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
        self.assertEqual(
            (self.root / "templates/example/ci.yml").read_text(),
            "expr: ${{ github.ref }}\n- run: mise run check\n",
        )

    def test_layout_rejects_multiple_consecutive_blank_lines(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/layouts/README.md.j2").write_text(
            "first section\n \n\t\nsecond section\n", encoding="utf-8"
        )
        self.write_config()

        with self.assertRaisesRegex(
            TemplateError,
            r"more than one consecutive blank line at output line 2: .*README\.md\.j2",
        ):
            TemplateRepository(self.root).render("example")

    def test_layout_allows_one_blank_line(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/layouts/README.md.j2").write_text(
            "first section\n\nsecond section\n", encoding="utf-8"
        )
        self.write_config()

        TemplateRepository(self.root).render("example")

        self.assertEqual(
            (self.root / "templates/example/README.md").read_text(),
            "first section\n\nsecond section\n",
        )

    def test_layout_rejects_multiple_leading_blank_lines(self) -> None:
        (self.root / "shared/layouts").mkdir(parents=True)
        (self.root / "shared/layouts/README.md.j2").write_text(
            "\n\nfirst section\n", encoding="utf-8"
        )
        self.write_config()

        with self.assertRaisesRegex(
            TemplateError,
            r"more than one consecutive blank line at output line 2: .*README\.md\.j2",
        ):
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

        self.assertEqual(
            (self.output_root / "disabled/ci.yml").read_text(), "steps:\n"
        )
        self.assertEqual(
            (self.output_root / "enabled/ci.yml").read_text(),
            "steps:\n- run: package\n",
        )

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

        self.assertEqual(
            (self.output_root / "disabled/Cargo.toml").read_text(),
            "[package]\npublish = false\n",
        )
        self.assertEqual(
            (self.output_root / "enabled/Cargo.toml").read_text(),
            '[package]\npublish = ["crates-io"]\n',
        )

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
            with self.subTest(declaration=declaration):
                self.write_config(
                    "docs-site = true\n"
                    "[templates.example.capability_outputs]\n"
                    + declaration
                )
                with self.assertRaisesRegex(TemplateError, message):
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

        with self.assertRaisesRegex(TemplateError, "requires an optional slot"):
            TemplateRepository(self.root).render("example")

    def test_every_capability_must_affect_an_output_or_slot_binding(self) -> None:
        self.write_config("unused = false\n")

        with self.assertRaisesRegex(
            TemplateError, "capability has no delivery effect.*unused"
        ):
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
            with self.subTest(body=body):
                self.write_config(body)
                with self.assertRaisesRegex(TemplateError, message):
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
            with self.subTest(declaration=declaration):
                self.write_config(
                    "release = false\n"
                    '[templates.example.slots."ci.yml"]\n'
                    'steps = { capability = "release", '
                    + declaration
                    + " }\n"
                )
                with self.assertRaisesRegex(TemplateError, message):
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
        self.assertFalse((snapshot / "release.yml").exists())
        self.assertTrue(repository.check("example").matches)

        repository.render_to(
            "example",
            self.output_root / "enabled",
            enabled_capabilities=("release",),
        )
        self.assertTrue((self.output_root / "enabled/release.yml").is_file())
        self.assertFalse((snapshot / "release.yml").exists())
        self.assertTrue(repository.check("example").matches)

    def test_directory_selector_does_not_match_same_named_file(self) -> None:
        self.write_config(
            "docs-site = true\n"
            "[templates.example.capability_outputs]\n"
            'docs-site = ["docs/"]\n'
        )
        (self.root / "shared/static/docs").write_text("file\n", encoding="utf-8")

        with self.assertRaisesRegex(TemplateError, "does not match any output"):
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

        with self.assertRaisesRegex(
            TemplateError, "matched by multiple capability output selectors"
        ):
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
            with self.subTest(declaration=declaration):
                self.write_config(
                    "release = false\n"
                    '[templates.example.slots."Cargo.toml"]\n'
                    'publish = { capability = "release", '
                    + declaration
                    + " }\n"
                )
                repository = TemplateRepository(self.root)
                with self.assertRaisesRegex(TemplateError, "invalid fragment reference"):
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
        with self.assertRaisesRegex(TemplateError, "does not bind required slot"):
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
        with self.assertRaisesRegex(TemplateError, "symlink escapes"):
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
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(
                    TemplateError, "destination must be outside repository-owned paths"
                ):
                    repository.render_to(
                        "example", destination, enabled_capabilities=()
                    )
        self.assertEqual(ancestor_marker.read_text(), "keep\n")
        ancestor_marker.unlink()

    def test_static_symlink_must_stay_inside_template(self) -> None:
        self.write_config()
        os.symlink("../outside", self.root / "shared/static/link")
        with self.assertRaisesRegex(TemplateError, "escapes"):
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
        with self.assertRaisesRegex(TemplateError, "missing required metadata"):
            TemplateRepository(self.root)

    def test_instantiation_profile_requires_complete_export_metadata(self) -> None:
        self.write_config()
        config = (self.root / "templates.toml").read_text(encoding="utf-8")
        (self.root / "templates.toml").write_text(
            config.replace('project_name = "REPLACE ME: project name"\n', ""),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(TemplateError, "invalid export metadata"):
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
        self.assertEqual(root_config["ignorePaths"], ["templates/**"])
        self.assertEqual(
            [rule["description"] for rule in root_config["packageRules"]],
            ["base", "root"],
        )
        self.assertEqual(template_config["enabledManagers"], ["npm"])
        self.assertEqual(
            [rule["description"] for rule in template_config["packageRules"]],
            ["base", "template"],
        )
        self.assertTrue(repository.check_repository().matches)
        self.assertTrue(repository.check("example").matches)

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

        with self.assertRaisesRegex(TemplateError, "duplicate top-level keys"):
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
        self.assertEqual(disabled["enabledManagers"], ["mise"])
        self.assertNotIn("packageRules", disabled)
        self.assertEqual(enabled["enabledManagers"], ["mise", "npm"])
        self.assertEqual(enabled["packageRules"][0]["description"], "documentation")

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
        with self.assertRaisesRegex(
            TemplateError, "contribution references undeclared capability"
        ):
            TemplateRepository(self.root).render("example")

    def test_docs_site_capability_renders_complete_profile_variants(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        repository = TemplateRepository(repository_root)

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            for template in ("common", "go-cli", "rust"):
                with self.subTest(template=template):
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

                    self.assertTrue((enabled / "docs/package.json").is_file())
                    self.assertTrue(
                        (enabled / ".github/workflows/docs.yml").is_file()
                    )
                    self.assertFalse((disabled / "docs").exists())
                    self.assertFalse(
                        (disabled / ".github/workflows/docs.yml").exists()
                    )

                    enabled_mise = (enabled / "mise.toml").read_text()
                    disabled_mise = (disabled / "mise.toml").read_text()
                    self.assertIn('node = "26"', enabled_mise)
                    self.assertIn('pnpm = "11"', enabled_mise)
                    self.assertIn("[tasks.'docs:build']", enabled_mise)
                    self.assertNotIn('node = "26"', disabled_mise)
                    self.assertNotIn('pnpm = "11"', disabled_mise)
                    self.assertNotIn("docs:build", disabled_mise)

                    enabled_ci = (enabled / ".github/workflows/ci.yml").read_text()
                    disabled_ci = (disabled / ".github/workflows/ci.yml").read_text()
                    self.assertIn("  docs:\n", enabled_ci)
                    self.assertNotIn("  docs:\n", disabled_ci)
                    self.assertEqual(enabled_ci, enabled_ci.rstrip() + "\n")
                    self.assertEqual(disabled_ci, disabled_ci.rstrip() + "\n")
                    self.assertEqual(enabled_mise, enabled_mise.rstrip() + "\n")
                    self.assertEqual(disabled_mise, disabled_mise.rstrip() + "\n")

                    enabled_readme = (enabled / "README.md").read_text()
                    disabled_readme = (disabled / "README.md").read_text()
                    self.assertIn("docs-online-blue", enabled_readme)
                    self.assertIn("## Documentation", enabled_readme)
                    self.assertNotIn("docs-online-blue", disabled_readme)
                    self.assertNotIn("## Documentation", disabled_readme)

                    enabled_contributing = (enabled / "CONTRIBUTING.md").read_text()
                    disabled_contributing = (
                        disabled / "CONTRIBUTING.md"
                    ).read_text()
                    self.assertIn("Documentation Site", enabled_contributing)
                    self.assertNotIn("Documentation Site", disabled_contributing)

                    enabled_gitignore = (enabled / ".gitignore").read_text()
                    disabled_gitignore = (disabled / ".gitignore").read_text()
                    self.assertIn("/docs/node_modules/", enabled_gitignore)
                    self.assertNotIn("/docs/node_modules/", disabled_gitignore)
                    self.assertFalse(disabled_gitignore.startswith("\n"))

                    enabled_renovate = json.loads(
                        (enabled / "renovate.json").read_text()
                    )
                    disabled_renovate = json.loads(
                        (disabled / "renovate.json").read_text()
                    )
                    self.assertIn("npm", enabled_renovate["enabledManagers"])
                    self.assertNotIn("npm", disabled_renovate["enabledManagers"])
                    self.assertTrue(
                        any(
                            rule.get("matchManagers") == ["npm"]
                            for rule in enabled_renovate["packageRules"]
                        )
                    )
                    self.assertFalse(
                        any(
                            rule.get("matchManagers") == ["npm"]
                            for rule in disabled_renovate["packageRules"]
                        )
                    )

    def test_export_metadata_instantiates_every_profile_and_derived_value(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        repository = TemplateRepository(repository_root)

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            for template in ("common", "go-cli", "rust"):
                with self.subTest(template=template):
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
                        self.assertNotRegex(
                            str(path.relative_to(output)), r"\{\{[A-Z]"
                        )
                        if path.is_file():
                            try:
                                content = path.read_text(encoding="utf-8")
                            except UnicodeDecodeError:
                                continue
                            self.assertNotRegex(content, r"\{\{[A-Z]")

                    if template == "go-cli":
                        self.assertTrue(
                            (output / "cmd/replace-me-binary/main.go").is_file()
                        )
                        self.assertEqual(
                            (output / "go.mod").read_text(encoding="utf-8").splitlines()[0],
                            "module example.invalid/replace-me-module",
                        )
                    if template == "rust":
                        cargo = (output / "Cargo.toml").read_text(encoding="utf-8")
                        main = (output / "src/main.rs").read_text(encoding="utf-8")
                        docs = (output / "docs/index.md").read_text(encoding="utf-8")
                        self.assertIn('description = "Replace \\"this\\" description"', cargo)
                        self.assertIn("replace_me_package::greeting", main)
                        self.assertIn('text: "Replace \\"this\\" description"', docs)

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
            self.assertEqual(disabled_cargo["package"]["publish"], False)
            self.assertEqual(enabled_cargo["package"]["publish"], ["crates-io"])
            self.assertEqual(
                enabled_cargo["package"]["description"],
                'Example "Rust" CLI description',
            )
            self.assertEqual(enabled_cargo["package"]["license"], "MIT")
            self.assertEqual(
                enabled_cargo["package"]["repository"],
                "https://github.com/YewFence/example-rust-cli",
            )
            self.assertEqual(enabled_cargo["package"]["readme"], "README.md")

            disabled_mise = (disabled / "mise.ci.toml").read_text()
            enabled_mise = (enabled / "mise.ci.toml").read_text()
            self.assertNotIn("crates-io:package:check", disabled_mise)
            self.assertNotIn("crates-io:publish", disabled_mise)
            self.assertNotIn('jq = "1"', disabled_mise)
            self.assertIn('[tasks."crates-io:package:check"]', enabled_mise)
            self.assertIn('run = "cargo package --locked"', enabled_mise)
            self.assertIn('[tasks."crates-io:publish"]', enabled_mise)
            self.assertIn('file = "scripts/publish-crate"', enabled_mise)
            self.assertIn('jq = "1"', enabled_mise)

            disabled_publish_script = disabled / "scripts/publish-crate"
            publish_script = enabled / "scripts/publish-crate"
            self.assertFalse(disabled_publish_script.exists())
            self.assertTrue(publish_script.stat().st_mode & stat.S_IXUSR)
            publish_script_text = publish_script.read_text()
            self.assertIn(
                "cargo metadata --locked --no-deps --format-version 1",
                publish_script_text,
            )
            self.assertIn(
                "--user-agent \"${crate_name}-publish "
                "(https://github.com/YewFence/example-rust-cli)\"",
                publish_script_text,
            )
            self.assertIn("https://crates.io/api/v1/crates/", publish_script_text)
            self.assertIn("cargo publish --dry-run", publish_script_text)
            self.assertIn(
                "crates.io trusted publishing did not provide a token",
                publish_script_text,
            )

            disabled_ci = (disabled / ".github/workflows/ci.yml").read_text()
            enabled_ci = (enabled / ".github/workflows/ci.yml").read_text()
            self.assertNotIn("crates-io:package:check", disabled_ci)
            self.assertIn("mise run crates-io:package:check", enabled_ci)
            self.assertIn("github.event_name == 'pull_request'", enabled_ci)

            self.assertFalse((disabled / "CRATES_IO_PUBLISHING.md").exists())
            self.assertFalse((enabled / "CRATES_IO_PUBLISHING.md").exists())

            release = (enabled / ".github/workflows/release.yml").read_text()
            disabled_release = (disabled / ".github/workflows/release.yml").read_text()
            self.assertNotIn("matrix.packages", release)
            self.assertNotIn("  publish-crate:\n", disabled_release)
            self.assertIn("  publish-crate:\n", release)
            self.assertIn("needs: [version, build, release]", release)
            self.assertNotIn("cargo metadata", release)
            self.assertNotIn("https://crates.io/api/v1/crates/", release)
            self.assertNotIn("cargo publish", release)
            self.assertIn("continue-on-error: true", release)
            self.assertIn("rust-lang/crates-io-auth-action@v1", release)
            self.assertIn("run: mise run crates-io:publish", release)
            self.assertLess(
                release.index("  publish-crate:\n"),
                release.index("  close-superseded-release-pr:\n"),
            )
            self.assertLess(
                release.index("uses: rust-lang/crates-io-auth-action@v1"),
                release.index("run: mise run crates-io:publish"),
            )

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
            self.assertNotIn("container:build", disabled_mise)
            self.assertNotIn("container:publish", disabled_mise)
            self.assertNotIn("aqua:ko-build/ko", disabled_mise)
            self.assertIn('"aqua:ko-build/ko" = "0.19"', enabled_mise)
            self.assertIn('[tasks."container:build"]', enabled_mise)
            self.assertIn("ko build --local --tags dev", enabled_mise)
            self.assertIn('CONTAINER_IMAGE_REPOSITORY:-ko.local', enabled_mise)
            self.assertIn(
                "CONTAINER_IMAGE_REPOSITORY must be a complete registry/repository name",
                enabled_mise,
            )
            self.assertIn('CONTAINER_IMAGE_PLATFORM:-', enabled_mise)
            self.assertIn('[tasks."container:publish"]', enabled_mise)
            self.assertIn("--bare --platform=all", enabled_mise)
            self.assertIn("tag_args+=(--tags latest)", enabled_mise)
            self.assertIn(
                "ghcr.io/YewFence/example-go-cli",
                enabled_mise,
            )
            self.assertIn("./cmd/example-go-cli", enabled_mise)
            self.assertNotIn("./cmd/your-cli", enabled_mise)

            disabled_release = (
                disabled / ".github/workflows/release.yml"
            ).read_text()
            release = (enabled / ".github/workflows/release.yml").read_text()
            self.assertNotIn("  publish-container:\n", disabled_release)
            self.assertNotIn("packages: write", disabled_release)
            self.assertNotIn("ko login ghcr.io", disabled_release)
            self.assertIn("  publish-container:\n", release)
            self.assertIn("needs: [version, release]", release)
            self.assertIn("packages: write", release)
            self.assertIn("ko login ghcr.io", release)
            self.assertIn(
                "CONTAINER_IMAGE_REPOSITORY: ghcr.io/YewFence/example-go-cli",
                release,
            )
            self.assertIn(
                "RELEASE_PRERELEASE: ${{ needs.version.outputs.prerelease }}",
                release,
            )
            self.assertIn("run: mise run container:publish", release)
            self.assertNotIn("ko build", release)
            self.assertLess(
                release.index("  release:\n"),
                release.index("  publish-container:\n"),
            )
            self.assertLess(
                release.index("ko login ghcr.io"),
                release.index("run: mise run container:publish"),
            )

            disabled_readme = (disabled / "README.md").read_text()
            enabled_readme = (enabled / "README.md").read_text()
            self.assertNotIn("## Container Image", disabled_readme)
            self.assertIn("## Container Image", enabled_readme)
            self.assertIn(
                "ghcr.io/YewFence/example-go-cli:vMAJOR.MINOR.PATCH",
                enabled_readme,
            )

            for output in ("Dockerfile", "ko.yaml", ".ko.yaml"):
                self.assertFalse((enabled / output).exists())


if __name__ == "__main__":
    unittest.main()
