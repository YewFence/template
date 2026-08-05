from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from template_tool import TemplateRepository
from template_tool.cli import _run_template_project_check


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


if __name__ == "__main__":
    unittest.main()
