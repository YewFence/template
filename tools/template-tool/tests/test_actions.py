from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from template_tool import TemplateError, TemplateRepository
from template_tool.actions import discover_action_sources, update_actions


class ActionsUpdateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / ".github/workflows").mkdir(parents=True)
        (self.root / "shared/static").mkdir(parents=True)
        (self.root / "overlays/example/static/.github/workflows").mkdir(
            parents=True
        )
        (self.root / "templates.toml").write_text(
            "version = 1\n[templates.example]\n", encoding="utf-8"
        )
        self.root_workflow = self.root / ".github/workflows/ci.yml"
        self.template_workflow = (
            self.root / "overlays/example/static/.github/workflows/ci.yml"
        )
        self.root_workflow.write_text("uses: owner/action@old\n", encoding="utf-8")
        self.template_workflow.write_text(
            "uses: owner/action@old\n", encoding="utf-8"
        )
        self.repository = TemplateRepository(self.root)
        self.repository.render("example")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def update_fixture(paths: tuple[Path, ...]) -> None:
        for path in paths:
            path.write_text(path.read_text().replace("@old", "@new"))

    def test_update_actions_only_rewrites_real_sources_and_rerenders(self) -> None:
        discovered = discover_action_sources(self.root)
        self.assertEqual(
            tuple(path.relative_to(self.root) for path in discovered),
            (
                Path(".github/workflows/ci.yml"),
                Path("overlays/example/static/.github/workflows/ci.yml"),
            ),
        )

        changed = update_actions(self.repository, self.update_fixture)

        self.assertEqual(
            changed,
            (
                Path(".github/workflows/ci.yml"),
                Path("overlays/example/static/.github/workflows/ci.yml"),
            ),
        )
        self.assertIn("@new", self.root_workflow.read_text())
        self.assertIn("@new", self.template_workflow.read_text())
        self.assertIn(
            "@new",
            (self.root / "templates/example/.github/workflows/ci.yml").read_text(),
        )
        self.assertTrue(self.repository.check("example").matches)

    def test_update_actions_rejects_new_files_before_writing_sources(self) -> None:
        def create_extra(paths: tuple[Path, ...]) -> None:
            self.update_fixture(paths)
            (paths[0].parent / "unexpected.yml").write_text("unexpected\n")

        with self.assertRaisesRegex(TemplateError, "changed its file set"):
            update_actions(self.repository, create_extra)
        self.assertIn("@old", self.root_workflow.read_text())
        self.assertIn("@old", self.template_workflow.read_text())

    def test_update_actions_rolls_back_sources_and_snapshots(self) -> None:
        def fail_validation() -> None:
            raise TemplateError("fixture validation failure")

        with self.assertRaisesRegex(TemplateError, "fixture validation"):
            update_actions(self.repository, self.update_fixture, fail_validation)
        self.assertIn("@old", self.root_workflow.read_text())
        self.assertIn("@old", self.template_workflow.read_text())
        self.assertIn(
            "@old",
            (self.root / "templates/example/.github/workflows/ci.yml").read_text(),
        )
        self.assertTrue(self.repository.check("example").matches)


if __name__ == "__main__":
    unittest.main()
