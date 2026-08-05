from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from template_tool import TemplateError, TemplateRepository


class TemplateRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "shared/static").mkdir(parents=True)
        (self.root / "overlays/example/static").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_config(self, body: str = "") -> None:
        (self.root / "templates.toml").write_text(
            "version = 1\n[templates.example]\n"
            + body
            + "[templates.example.instantiation]\n"
            'required = ["project_name"]\n'
            "[templates.example.instantiation.tokens]\n"
            'PROJECT_NAME = "project_name"\n'
            "[templates.example.instantiation.validation.metadata]\n"
            'project_name = "Example Project"\n',
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

    def test_static_symlink_must_stay_inside_template(self) -> None:
        self.write_config()
        os.symlink("../outside", self.root / "shared/static/link")
        with self.assertRaisesRegex(TemplateError, "escapes"):
            TemplateRepository(self.root).render("example")

    def test_instantiation_profile_requires_valid_validation_metadata(self) -> None:
        (self.root / "templates.toml").write_text(
            "version = 1\n"
            "[templates.example.instantiation]\n"
            'required = ["project_name"]\n'
            "[templates.example.instantiation.tokens]\n"
            'PROJECT_NAME = "project_name"\n'
            "[templates.example.instantiation.validation.metadata]\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(TemplateError, "missing required metadata"):
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


if __name__ == "__main__":
    unittest.main()
