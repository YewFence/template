from __future__ import annotations

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
            "version = 1\n[templates.example]\n" + body,
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

    def test_lock_update_rewrites_declared_outputs_and_rerenders(self) -> None:
        self.write_config(
            '[templates.example.locks]\n'
            'outputs = ["state.lock"]\n'
        )
        source = self.root / "overlays/example/static/state.lock"
        source.write_text("before\n", encoding="utf-8")
        repository = TemplateRepository(self.root)
        repository.render("example")

        calls: list[tuple[Path, bool]] = []

        def adapter(staging: Path, bump: bool) -> None:
            calls.append((staging, bump))
            (staging / "state.lock").write_text("after\n", encoding="utf-8")

        repository.update_locks("example", True, adapter)
        self.assertEqual(calls[0][1], True)
        self.assertEqual(source.read_text(), "after\n")
        self.assertEqual(
            (self.root / "templates/example/state.lock").read_text(), "after\n"
        )
        self.assertTrue(repository.check("example").matches)

    def test_lock_update_rejects_undeclared_changes_without_touching_sources(self) -> None:
        self.write_config(
            '[templates.example.locks]\n'
            'outputs = ["state.lock"]\n'
        )
        source = self.root / "overlays/example/static/state.lock"
        source.write_text("before\n", encoding="utf-8")
        repository = TemplateRepository(self.root)
        repository.render("example")
        target = self.root / "templates/example/state.lock"

        def adapter(staging: Path, bump: bool) -> None:
            (staging / "state.lock").write_text("after\n", encoding="utf-8")
            (staging / "unexpected").write_text("forbidden\n", encoding="utf-8")

        with self.assertRaisesRegex(TemplateError, "undeclared"):
            repository.update_locks("example", False, adapter)
        self.assertEqual(source.read_text(), "before\n")
        self.assertEqual(target.read_text(), "before\n")

    def test_lock_update_rejects_symlink_outputs_and_rolls_back_validation(self) -> None:
        self.write_config(
            '[templates.example.locks]\n'
            'outputs = ["state.lock"]\n'
        )
        source = self.root / "overlays/example/static/state.lock"
        source.write_text("before\n", encoding="utf-8")
        repository = TemplateRepository(self.root)
        repository.render("example")
        target = self.root / "templates/example/state.lock"

        def adapter(staging: Path, bump: bool) -> None:
            (staging / "state.lock").unlink()
            os.symlink("missing", staging / "state.lock")

        with self.assertRaisesRegex(TemplateError, "regular file"):
            repository.update_locks("example", False, adapter)
        self.assertEqual(source.read_text(), "before\n")
        self.assertEqual(target.read_text(), "before\n")

    def test_lock_update_rolls_back_after_final_validation_failure(self) -> None:
        self.write_config(
            '[templates.example.locks]\n'
            'outputs = ["state.lock"]\n'
        )
        source = self.root / "overlays/example/static/state.lock"
        source.write_text("before\n", encoding="utf-8")
        repository = TemplateRepository(self.root)
        repository.render("example")
        target = self.root / "templates/example/state.lock"

        def adapter(staging: Path, bump: bool) -> None:
            (staging / "state.lock").write_text("after\n", encoding="utf-8")

        def fail_validation(template: str) -> None:
            raise TemplateError("fixture validation failure")

        with self.assertRaisesRegex(TemplateError, "fixture validation"):
            repository.update_locks("example", False, adapter, fail_validation)
        self.assertEqual(source.read_text(), "before\n")
        self.assertEqual(target.read_text(), "before\n")


if __name__ == "__main__":
    unittest.main()
