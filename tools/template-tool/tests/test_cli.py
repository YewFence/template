from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

from template_tool import TemplateRepository
from template_tool.cli import (
    ApplicationError,
    TemplateError,
    _collect_metadata,
    _metadata_from_args,
    _run_template_project_check,
    check_main,
)

REPOSITORY_ROOT = Path(__file__).parents[3]


class TemplateCheckTest(unittest.TestCase):
    @mock.patch("template_tool.cli._run_template_project_check")
    def test_repository_check_expands_the_configured_ten_cases(
        self, run_check: mock.Mock
    ) -> None:
        check_main(["--root", str(REPOSITORY_ROOT)])

        self.assertEqual(len(run_check.call_args_list), 10)
        self.assertEqual(
            [call.args[1:] for call in run_check.call_args_list],
            [
                ("common", ()),
                ("common", ("docs-site",)),
                ("go-cli", ()),
                ("go-cli", ("docs-site",)),
                ("go-cli", ("container-image-publish",)),
                ("go-cli", ("container-image-publish", "docs-site")),
                ("rust", ()),
                ("rust", ("docs-site",)),
                ("rust", ("crates-io-publish",)),
                ("rust", ("crates-io-publish", "docs-site")),
            ],
        )

    @mock.patch("template_tool.cli._run_template_project_check")
    @mock.patch("template_tool.cli.TemplateRepository")
    def test_check_runs_every_capability_combination_and_summarizes_failures(
        self, repository_type: mock.Mock, run_check: mock.Mock
    ) -> None:
        repository = repository_type.return_value
        repository.select.return_value = ("example",)
        repository.check_repository.return_value.matches = True
        repository.check.return_value.matches = True
        repository.capabilities.return_value = (
            ("docs-site", True),
            ("release", False),
        )
        run_check.side_effect = (
            None,
            TemplateError("overlay check exited with 7"),
            None,
            None,
        )
        stderr = StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            check_main(["example", "--root", "/repository"])

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(
            run_check.call_args_list,
            [
                mock.call(repository, "example", ()),
                mock.call(repository, "example", ("release",)),
                mock.call(repository, "example", ("docs-site",)),
                mock.call(repository, "example", ("docs-site", "release")),
            ],
        )
        self.assertIn(
            "staging validation failures:\n",
            stderr.getvalue(),
        )
        self.assertIn(
            "example[docs-site=off,release=on]: overlay check exited with 7",
            stderr.getvalue(),
        )

    def test_project_check_uses_external_git_environment_without_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "shared/static").mkdir(parents=True)
            (root / "overlays/example/static").mkdir(parents=True)
            (root / "templates.toml").write_text(
                "version = 2\n"
                "[templates.example.capabilities]\n"
                "docs-site = true\n"
                "release = false\n"
                "[templates.example.capability_outputs]\n"
                'docs-site = ["docs.txt"]\n'
                'release = ["release.txt"]\n'
                "[templates.example.instantiation]\n"
                'required = ["project_name"]\n'
                "[templates.example.instantiation.tokens]\n"
                'PROJECT_NAME = "project_name"\n'
                "[templates.example.instantiation.validation.metadata]\n"
                'project_name = "Example Project"\n'
                "[templates.example.instantiation.export.metadata]\n"
                'project_name = "REPLACE ME: project name"\n',
                encoding="utf-8",
            )
            (root / "shared/static/.gitignore").write_text("cache/\n", encoding="utf-8")
            (root / "shared/static/tracked").write_text("tracked\n", encoding="utf-8")
            (root / "overlays/example/static/docs.txt").write_text(
                "documentation\n", encoding="utf-8"
            )
            (root / "overlays/example/static/release.txt").write_text(
                "release\n", encoding="utf-8"
            )

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
                "test \"$TEMPLATE_TOOL_ENABLED_CAPABILITIES\" = '[\"docs-site\",\"release\"]'\n"
                "test -f \"$template_root/docs.txt\"\n"
                "test -f \"$template_root/release.txt\"\n"
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
                _run_template_project_check(
                    repository, "example", ("release", "docs-site")
                )

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
