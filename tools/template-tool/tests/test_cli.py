from __future__ import annotations

import os
import tempfile
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from template_tool import TemplateRepository
from template_tool.cli import (
    ApplicationError,
    TemplateError,
    _collect_metadata,
    _isolate_mise_global_config,
    _metadata_from_args,
    _run_template_project_check,
    check_main,
)

REPOSITORY_ROOT = Path(__file__).parents[3]


class TestTemplateCheck:
    @pytest.mark.parametrize(
        ("environment", "expected"),
        (
            (
                {
                    "MISE_CONFIG_DIR": "/custom/mise",
                    "MISE_GLOBAL_CONFIG_FILE": "/dev/null",
                    "MISE_IGNORED_CONFIG_PATHS": "/existing:/custom/mise",
                },
                {
                    "MISE_CONFIG_DIR": "/custom/mise",
                    "MISE_IGNORED_CONFIG_PATHS": "/existing:/custom/mise",
                },
            ),
            (
                {
                    "XDG_CONFIG_HOME": "/xdg",
                    "MISE_GLOBAL_CONFIG_FILE": "/custom/global.toml",
                    "MISE_IGNORED_CONFIG_PATHS": "/existing",
                },
                {
                    "XDG_CONFIG_HOME": "/xdg",
                    "MISE_IGNORED_CONFIG_PATHS": "/xdg/mise:/existing:/custom/global.toml",
                },
            ),
        ),
    )
    def test_isolate_mise_global_config_uses_supported_ignores(
        self, environment: dict[str, str], expected: dict[str, str]
    ) -> None:
        _isolate_mise_global_config(environment)

        assert "MISE_GLOBAL_CONFIG_FILE" not in environment
        assert environment == expected

    def test_isolate_mise_global_config_defaults_to_user_config_directory(self) -> None:
        environment: dict[str, str] = {}

        _isolate_mise_global_config(environment)

        assert environment["MISE_IGNORED_CONFIG_PATHS"] == str(
            Path.home() / ".config/mise"
        )

    def test_check_runs_every_capability_combination_and_summarizes_failures(
        self, mocker: MockerFixture
    ) -> None:
        repository_type = mocker.patch("template_tool.cli.TemplateRepository")
        run_check = mocker.patch("template_tool.cli._run_template_project_check")
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

        with redirect_stderr(stderr), pytest.raises(SystemExit) as raised:
            check_main(["example", "--root", "/repository"])

        assert raised.value.code == 1
        assert run_check.call_args_list == [
            mocker.call(repository, "example", ()),
            mocker.call(repository, "example", ("release",)),
            mocker.call(repository, "example", ("docs-site",)),
            mocker.call(repository, "example", ("docs-site", "release")),
        ]
        assert "staging validation failures:\n" in stderr.getvalue()
        assert (
            "example[docs-site=off,release=on]: overlay check exited with 7"
            in stderr.getvalue()
        )

    def test_project_check_uses_external_git_environment_without_marker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
                "test \"$1\" = run\n"
                "test \"$2\" = //overlays/example:check\n"
                "template_root=$3\n"
                "test \"$TEMPLATE_TOOL_ENABLED_CAPABILITIES\" = '[\"docs-site\",\"release\"]'\n"
                "test \"$MISE_CEILING_PATHS\" = \"$(dirname \"$PWD\")\"\n"
                "test \"$TEMPLATE_TOOL_REPOSITORY_ROOT\" = \"$PWD\"\n"
                "test -z \"${MISE_GLOBAL_CONFIG_FILE:-}\"\n"
                "test \"$MISE_IGNORED_CONFIG_PATHS\" = '/tmp/mise-global:/tmp/existing-ignore'\n"
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
                "PATH": f"{binary_directory}:{os.environ['PATH']}",
                "MISE_CONFIG_DIR": "/tmp/mise-global",
                "MISE_GLOBAL_CONFIG_FILE": "/dev/null",
                "MISE_IGNORED_CONFIG_PATHS": "/tmp/existing-ignore",
            }
            for key in tuple(os.environ):
                monkeypatch.delenv(key, raising=False)
            for key, value in environment.items():
                monkeypatch.setenv(key, value)
            _run_template_project_check(
                repository, "example", ("release", "docs-site")
            )

            assert not (root / "templates/example/.git").exists()

    def test_metadata_from_args_preserves_only_supplied_values(self) -> None:
        args = type(
            "Args",
            (),
            {
                "project_name": "Example",
                "description": None,
                "github_owner": "YewFence",
                "repo_name": None,
                "python_package": None,
                "go_module": None,
                "cargo_package": None,
                "binary_name": None,
            },
        )()

        assert _metadata_from_args(args) == {
            "project_name": "Example",
            "github_owner": "YewFence",
        }

    def test_interactive_metadata_retries_invalid_value(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch("template_tool.cli.required_metadata", return_value=("project_name",))
        text = mocker.patch("template_tool.cli.questionary.text")
        confirm = mocker.patch("template_tool.cli.questionary.confirm")
        text.side_effect = [
            mocker.Mock(ask=mocker.Mock(return_value=" bad ")),
            mocker.Mock(ask=mocker.Mock(return_value="Good")),
        ]
        confirm.return_value.ask.return_value = True

        metadata = _collect_metadata("repo", "ref", "example", {})

        assert metadata == {"project_name": "Good"}
        assert text.call_count == 2
        confirm.return_value.ask.assert_called_once()

    def test_interactive_metadata_cancel_does_not_return_values(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch("template_tool.cli.required_metadata", return_value=("project_name",))
        text = mocker.patch("template_tool.cli.questionary.text")
        confirm = mocker.patch("template_tool.cli.questionary.confirm")
        text.return_value.ask.return_value = "Good"
        confirm.return_value.ask.return_value = False

        with pytest.raises(ApplicationError, match="cancelled"):
            _collect_metadata("repo", "ref", "example", {})
