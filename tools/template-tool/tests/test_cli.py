from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from template_tool import TemplateRepository
from template_tool.cli import ApplicationError, _collect_metadata, _metadata_from_args, _run_template_project_check


class TemplateCheckTest(unittest.TestCase):
    def test_project_check_uses_external_git_environment_without_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "shared/static").mkdir(parents=True)
            (root / "overlays/example/static").mkdir(parents=True)
            (root / "templates.toml").write_text(
                "version = 1\n"
                "[templates.example.instantiation]\n"
                'required = ["project_name"]\n'
                "[templates.example.instantiation.tokens]\n"
                'PROJECT_NAME = "project_name"\n'
                "[templates.example.instantiation.validation.metadata]\n"
                'project_name = "Example Project"\n',
                encoding="utf-8",
            )
            (root / "shared/static/.gitignore").write_text("cache/\n", encoding="utf-8")
            (root / "shared/static/tracked").write_text("tracked\n", encoding="utf-8")

            repository = TemplateRepository(root)
            repository.render("example")
            cache = root / "templates/example/cache"
            cache.mkdir()
            (cache / "artifact").write_text("ignored\n", encoding="utf-8")

            binary_directory = root / "bin"
            binary_directory.mkdir()
            mise = binary_directory / "mise"
            mise.write_text(
                "#!/bin/sh\n"
                "set -eu\n"
                "template_root=$3\n"
                "test ! -e \"$template_root/.git\"\n"
                "test \"$(git -C \"$template_root\" rev-parse --is-inside-work-tree)\" = true\n"
                "test -z \"$(git -C \"$template_root\" ls-files cache)\"\n"
                "git -C \"$template_root\" diff --quiet\n"
                "git -C \"$template_root\" diff --cached --quiet\n",
                encoding="utf-8",
            )
            mise.chmod(0o755)

            environment = os.environ | {
                "PATH": f"{binary_directory}:{os.environ['PATH']}"
            }
            with mock.patch.dict(os.environ, environment, clear=True):
                _run_template_project_check(repository, "example")

            self.assertFalse((root / "templates/example/.git").exists())

    def test_metadata_from_args_preserves_only_supplied_values(self) -> None:
        args = type(
            "Args",
            (),
            {
                "project_name": "Example",
                "description": None,
                "github_owner": "YewFence",
                "repo_name": None,
                "go_module": None,
                "cargo_package": None,
                "binary_name": None,
            },
        )()

        self.assertEqual(
            _metadata_from_args(args),
            {"project_name": "Example", "github_owner": "YewFence"},
        )

    @mock.patch("template_tool.cli.questionary.confirm")
    @mock.patch("template_tool.cli.questionary.text")
    @mock.patch("template_tool.cli.required_metadata", return_value=("project_name",))
    def test_interactive_metadata_retries_invalid_value(
        self, required: mock.Mock, text: mock.Mock, confirm: mock.Mock
    ) -> None:
        text.side_effect = [
            mock.Mock(ask=mock.Mock(return_value=" bad ")),
            mock.Mock(ask=mock.Mock(return_value="Good")),
        ]
        confirm.return_value.ask.return_value = True

        metadata = _collect_metadata("repo", "ref", "example", {})

        self.assertEqual(metadata, {"project_name": "Good"})
        self.assertEqual(text.call_count, 2)
        confirm.return_value.ask.assert_called_once()

    @mock.patch("template_tool.cli.questionary.confirm")
    @mock.patch("template_tool.cli.questionary.text")
    @mock.patch("template_tool.cli.required_metadata", return_value=("project_name",))
    def test_interactive_metadata_cancel_does_not_return_values(
        self, required: mock.Mock, text: mock.Mock, confirm: mock.Mock
    ) -> None:
        text.return_value.ask.return_value = "Good"
        confirm.return_value.ask.return_value = False

        with self.assertRaisesRegex(ApplicationError, "cancelled"):
            _collect_metadata("repo", "ref", "example", {})


if __name__ == "__main__":
    unittest.main()
