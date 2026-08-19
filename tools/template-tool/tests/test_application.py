from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from template_tool.application import (
    ApplicationError,
    apply_selected_template,
    apply_template,
    export_template,
    initialize_project,
    select_template,
)
from template_tool.bootstrap import capabilities_main as bootstrap_capabilities_main
from template_tool.bootstrap import export_main as bootstrap_export_main
from template_tool.cli import apply_main, capabilities_main, export_main, init_main, main


class TestApplyTemplate:
    def setup_method(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source"
        self.target = self.root / "target"
        self._init_source()

    def teardown_method(self) -> None:
        self.temporary_directory.cleanup()

    def _git(self, repository: Path, *arguments: str, capture: bool = False) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            text=True,
            capture_output=capture,
        )
        return completed.stdout.strip() if capture else ""

    def _configure_identity(self, repository: Path) -> None:
        self._git(repository, "config", "user.name", "Template Test")
        self._git(repository, "config", "user.email", "template-test@localhost")
        self._git(repository, "config", "commit.gpgSign", "false")

    def _init_source(self) -> None:
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", str(self.source)],
            check=True,
        )
        self._configure_identity(self.source)
        (self.source / "tools/template-tool").mkdir(parents=True)
        (self.source / "scripts").mkdir()
        (self.source / "overlays/example/static").mkdir(parents=True)
        (self.source / "templates/example").mkdir(parents=True)
        (self.source / "tools/template-tool/README").write_text("tool\n")
        (self.source / "scripts/apply-template").write_text("launcher\n")
        (self.source / "templates.toml").write_text(
            "version = 2\n"
            "[apply]\n"
            'protected = [".gitignore", "AGENTS.*", "LICENSE*"]\n'
            'hints = ["Review protected files manually."]\n'
            "[templates.example.capabilities]\n"
            "docs-site = false\n"
            "release = false\n"
            "[templates.example.capability_outputs]\n"
            'docs-site = ["docs.txt"]\n'
            'release = ["release.txt"]\n'
            "[templates.example.instantiation]\n"
            'required = ["project_name", "binary_name"]\n'
            "[templates.example.instantiation.tokens]\n"
            'PROJECT_NAME = "project_name"\n'
            'BINARY_NAME = "binary_name"\n'
            "[templates.example.instantiation.derived.PROJECT_NAME_JSON]\n"
            'source = "project_name"\n'
            'transform = "json-string"\n'
            "[templates.example.instantiation.validation.metadata]\n"
            'project_name = "Validation Project"\n'
            'binary_name = "validation-project"\n'
            "[templates.example.instantiation.export.metadata]\n"
            'project_name = "REPLACE ME: project name"\n'
            'binary_name = "replace-me-binary"\n',
            encoding="utf-8",
        )
        source_root = self.source / "overlays/example/static"
        (source_root / ".gitignore").write_text("template-cache/\n")
        (source_root / "AGENTS.md").write_text("template agents\n")
        (source_root / "LICENSE").write_text("template license\n")
        (source_root / "docs.txt").write_text("documentation\n")
        (source_root / "release.txt").write_text("release\n")
        (source_root / "project.toml").write_text(
            'name = {{PROJECT_NAME_JSON}}\nenabled = true\n'
        )
        command = source_root / "cmd/{{BINARY_NAME}}/main.txt"
        command.parent.mkdir(parents=True)
        command.write_text("{{PROJECT_NAME}}\n", encoding="utf-8")
        (self.source / "templates/example/preview-only.txt").write_text(
            "stale preview\n", encoding="utf-8"
        )
        self._git(self.source, "add", "--all")
        self._git(self.source, "commit", "--quiet", "-m", "template fixture")

    def _init_target(self, files: dict[str, str] | None = None) -> str:
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", str(self.target)],
            check=True,
        )
        self._configure_identity(self.target)
        for relative, content in (files or {"existing.txt": "existing\n"}).items():
            path = self.target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self._git(self.target, "add", "--all")
        self._git(self.target, "commit", "--quiet", "-m", "target baseline")
        return self._git(self.target, "rev-parse", "HEAD", capture=True)

    def test_apply_stages_template_and_skips_protected_root_paths(self) -> None:
        head = self._init_target(
            {
                ".gitignore": ".jj/\ntarget-cache/\n",
                "AGENTS.md": "target agents\n",
                "LICENSE": "target license\n",
            }
        )
        (self.target / ".jj").mkdir()
        self._git(self.target, "checkout", "--detach", "--quiet")

        result = apply_template(
            str(self.source), "main", "example", self.target, keep_tokens=True
        )

        assert not (result.conflicted)
        assert result.jujutsu
        assert (result.hints) == (("Review protected files manually.",))
        assert (result.skipped) == ((".gitignore", "AGENTS.md", "LICENSE"))
        assert ((self.target / ".gitignore").read_text()) == (".jj/\ntarget-cache/\n")
        assert ((self.target / "AGENTS.md").read_text()) == ("target agents\n")
        assert ((self.target / "LICENSE").read_text()) == ("target license\n")
        assert ((self.target / "project.toml").read_text()) == ('name = {{PROJECT_NAME_JSON}}\nenabled = true\n')
        assert (self._git(self.target, "diff", "--cached", "--name-only", capture=True)) == ("cmd/{{BINARY_NAME}}/main.txt\nproject.toml")
        assert not ((self.target / "preview-only.txt").exists())
        assert (self._git(self.target, "rev-parse", "HEAD", capture=True)) == (head)
        assert not ((self.target / ".git/MERGE_HEAD").exists())

    def test_apply_instantiates_fetched_template_tree(self) -> None:
        self._init_target()

        result = apply_template(
            str(self.source),
            "main",
            "example",
            self.target,
            metadata={
                "project_name": 'Applied "Project"',
                "binary_name": "applied-project",
            },
            keep_tokens=False,
        )

        assert result.instantiated
        assert ((self.target / "project.toml").read_text()) == ('name = "Applied \\"Project\\""\nenabled = true\n')
        assert ((self.target / "cmd/applied-project/main.txt").read_text()) == ('Applied "Project"\n')
        assert (self._git(self.target, "diff", "--cached", "--name-only", capture=True)) == ("cmd/applied-project/main.txt\nproject.toml")
        assert not ((self.target / "preview-only.txt").exists())

    def test_apply_requires_complete_metadata_unless_keep_tokens(self) -> None:
        self._init_target()

        with pytest.raises(ApplicationError, match="missing required metadata: binary_name, project_name"):
            apply_template(
                str(self.source),
                "main",
                "example",
                self.target,
                metadata={},
                keep_tokens=False,
            )

    def test_apply_keep_tokens_rejects_invalid_capability_contract(self) -> None:
        config = (self.source / "templates.toml").read_text()
        (self.source / "templates.toml").write_text(
            config.replace(
                "[templates.example.capabilities]\n",
                "[templates.example.capabilities]\nDocs-Site = true\n",
            )
        )
        self._git(self.source, "add", "templates.toml")
        self._git(self.source, "commit", "--quiet", "-m", "invalid capability")
        self._init_target()

        with pytest.raises(ApplicationError, match="invalid capability name"):
            apply_template(
                str(self.source), "main", "example", self.target, keep_tokens=True
            )

        assert not (self._git(self.target, "status", "--porcelain", capture=True))

    def test_selected_source_checkout_stays_unchanged_while_preparing_application(self) -> None:
        self._init_target()
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            with select_template(str(self.source), "main", temporary_root) as selected:
                before = self._git(selected.source, "count-objects", "-v", capture=True)
                apply_selected_template(
                    selected, "example", self.target, keep_tokens=True
                )
                after = self._git(selected.source, "count-objects", "-v", capture=True)

        assert (after) == (before)

    def test_conflict_preserves_index_can_be_cancelled_and_resolved(self) -> None:
        (self.source / "overlays/example/static/README.md").write_text("template\n")
        self._git(self.source, "add", "overlays/example/static/README.md")
        self._git(self.source, "commit", "--quiet", "-m", "add template readme")
        head = self._init_target({"README.md": "target\n"})

        result = apply_template(
            str(self.source), "main", "example", self.target, keep_tokens=True
        )

        assert result.conflicted
        assert self._git(self.target, "ls-files", "-u", capture=True)
        assert not ((self.target / ".git/MERGE_HEAD").exists())
        self._git(self.target, "reset", "--hard", "HEAD")
        assert not (self._git(self.target, "status", "--porcelain", capture=True))
        assert (self._git(self.target, "rev-parse", "HEAD", capture=True)) == (head)

        result = apply_template(
            str(self.source), "main", "example", self.target, keep_tokens=True
        )
        assert result.conflicted
        (self.target / "README.md").write_text("resolved\n")
        self._git(self.target, "add", "README.md")
        self._git(self.target, "commit", "--quiet", "-m", "apply template")
        parents = self._git(
            self.target, "rev-list", "--parents", "-n", "1", "HEAD", capture=True
        ).split()
        assert (len(parents)) == (2)

    def test_dirty_unborn_and_in_progress_repositories_are_rejected(self) -> None:
        self._init_target()
        (self.target / "dirty.txt").write_text("dirty\n")
        with pytest.raises(ApplicationError, match="not clean"):
            apply_template(
                str(self.source), "main", "example", self.target, keep_tokens=True
            )

        unborn = self.root / "unborn"
        subprocess.run(["git", "init", "--quiet", str(unborn)], check=True)
        with pytest.raises(ApplicationError, match="at least one commit"):
            apply_template(
                str(self.source), "main", "example", unborn, keep_tokens=True
            )

        (self.target / "dirty.txt").unlink()
        (self.target / ".git/REVERT_HEAD").write_text("marker\n")
        with pytest.raises(ApplicationError, match="REVERT_HEAD"):
            apply_template(
                str(self.source), "main", "example", self.target, keep_tokens=True
            )

    def test_cli_rejects_dirty_repository_before_interactive_metadata(
        self, mocker: MockerFixture
    ) -> None:
        collect_metadata = mocker.patch("template_tool.cli._collect_metadata")
        self._init_target()
        (self.target / "dirty.txt").write_text("dirty\n")
        collect_metadata.return_value = {
            "project_name": "Example",
            "binary_name": "example",
        }
        stderr = StringIO()

        with redirect_stderr(stderr), pytest.raises(SystemExit) as exit_context:
            apply_main(
                [
                    str(self.target),
                    "--repo",
                    str(self.source),
                    "--ref",
                    "main",
                    "--template",
                    "example",
                    "--interactive",
                ]
            )

        assert (exit_context.value.code) == (1)
        assert ("target repository is not clean") in (stderr.getvalue())
        collect_metadata.assert_not_called()

    def test_cli_returns_nonzero_and_prints_conflict_recovery_hints(self) -> None:
        (self.source / "overlays/example/static/README.md").write_text("template\n")
        self._git(self.source, "add", "overlays/example/static/README.md")
        self._git(self.source, "commit", "--quiet", "-m", "add template readme")
        self._init_target({"README.md": "target\n"})
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            with pytest.raises(SystemExit) as exit_context:
                apply_main(
                    [
                        str(self.target),
                        "--repo",
                        str(self.source),
                        "--ref",
                        "main",
                        "--template",
                        "example",
                        "--enable-capability",
                        "release",
                        "--enable-capability",
                        "docs-site",
                        "--keep-tokens",
                    ]
                )

        assert (exit_context.value.code) == (1)
        assert ("Template-Commit:") in (stdout.getvalue())
        assert ("Capabilities: docs-site, release") in (stdout.getvalue())
        assert ("git status") in (stdout.getvalue())
        assert ("git diff --check") in (stdout.getvalue())
        assert ("git reset --hard HEAD") in (stdout.getvalue())
        assert not ((self.target / ".git/MERGE_HEAD").exists())

    def test_cli_rejects_keep_tokens_with_metadata(self) -> None:
        self._init_target()
        stderr = StringIO()

        with redirect_stderr(stderr), pytest.raises(SystemExit) as exit_context:
            apply_main(
                [
                    str(self.target),
                    "--repo",
                    str(self.source),
                    "--ref",
                    "main",
                    "--template",
                    "example",
                    "--keep-tokens",
                    "--project-name",
                    "Example",
                ]
            )

        assert (exit_context.value.code) == (1)
        assert ("cannot be combined") in (stderr.getvalue())
        assert not (self._git(self.target, "status", "--porcelain", capture=True))

    def test_apply_cli_disables_default_capability_without_deleting_target_content(
        self,
    ) -> None:
        config = (self.source / "templates.toml").read_text(encoding="utf-8")
        enabled_by_default = config.replace(
            "docs-site = false\n", "docs-site = true\n"
        )
        assert (enabled_by_default) != (config)
        (self.source / "templates.toml").write_text(
            enabled_by_default,
            encoding="utf-8",
        )
        self._git(self.source, "add", "templates.toml")
        self._git(self.source, "commit", "--quiet", "-m", "enable docs by default")
        head = self._init_target(
            {
                ".gitignore": "target-cache/\n",
                "AGENTS.md": "target agents\n",
                "LICENSE": "target license\n",
                "docs.txt": "target documentation\n",
            }
        )
        stdout = StringIO()

        with redirect_stdout(stdout):
            apply_main(
                [
                    str(self.target),
                    "--repo",
                    str(self.source),
                    "--ref",
                    "main",
                    "--template",
                    "example",
                    "--enable-capability",
                    "release",
                    "--enable-capability",
                    "release",
                    "--disable-capability",
                    "docs-site",
                    "--keep-tokens",
                ]
            )

        assert ("Capabilities: release\n") in (stdout.getvalue())
        assert ("HINT: skipped protected root paths: .gitignore, AGENTS.md, LICENSE") in (stdout.getvalue())
        assert (self.target / "release.txt").is_file()
        assert ("{{PROJECT_NAME_JSON}}") in ((self.target / "project.toml").read_text(encoding="utf-8"))
        assert ((self.target / "docs.txt").read_text(encoding="utf-8")) == ("target documentation\n")
        assert ((self.target / ".gitignore").read_text()) == ("target-cache/\n")
        assert ((self.target / "AGENTS.md").read_text()) == ("target agents\n")
        assert ((self.target / "LICENSE").read_text()) == ("target license\n")
        assert (self._git(self.target, "diff", "--cached", "--name-only", capture=True)) == ("cmd/{{BINARY_NAME}}/main.txt\nproject.toml\nrelease.txt")
        assert (self._git(self.target, "rev-parse", "HEAD", capture=True)) == (head)
        assert not ((self.target / ".git/MERGE_HEAD").exists())

    def test_apply_cli_rejects_unknown_and_conflicting_capability_overrides_before_mutation(self) -> None:
        self._init_target()
        for overrides, message in (
            (("--enable-capability", "unknown"), "not applicable"),
            (
                (
                    "--enable-capability",
                    "release",
                    "--disable-capability",
                    "release",
                ),
                "both enabled and disabled",
            ),
        ):
            stderr = StringIO()

            with redirect_stderr(stderr), pytest.raises(SystemExit) as raised:
                apply_main(
                    [
                        str(self.target),
                        "--repo",
                        str(self.source),
                        "--ref",
                        "main",
                        "--template",
                        "example",
                        *overrides,
                        "--keep-tokens",
                    ]
                )

            assert (raised.value.code) == (1)
            assert (message) in (stderr.getvalue())
            assert not (self._git(self.target, "status", "--porcelain", capture=True))

    def test_init_interactive_orders_capabilities_metadata_and_single_summary_confirmation(
        self, mocker: MockerFixture
    ) -> None:
        confirm = mocker.patch("template_tool.cli.questionary.confirm")
        text = mocker.patch("template_tool.cli.questionary.text")
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", str(self.target)],
            check=True,
        )
        self._configure_identity(self.target)
        events: list[str] = []
        confirmation_answers = iter((True, True))
        metadata_answers = iter(("Interactive Project", "interactive-project"))

        def confirm_prompt(message: str, *, default: bool):
            events.append(f"confirm:{message}")
            return mocker.Mock(
                ask=mocker.Mock(return_value=next(confirmation_answers))
            )

        def text_prompt(message: str):
            events.append(f"text:{message}")
            return mocker.Mock(ask=mocker.Mock(return_value=next(metadata_answers)))

        confirm.side_effect = confirm_prompt
        text.side_effect = text_prompt
        stdout = StringIO()

        with redirect_stdout(stdout):
            init_main(
                [
                    str(self.target),
                    "--repo",
                    str(self.source),
                    "--ref",
                    "main",
                    "--template",
                    "example",
                    "--enable-capability",
                    "release",
                    "--interactive",
                ]
            )

        assert ([event.split(":", 1)[0] for event in events]) == (["confirm", "text", "text", "confirm"])
        assert ("docs-site") in (events[0])
        assert ("release") not in (events[0])
        assert ("Template: example") in (events[-1])
        assert ("Capabilities: docs-site, release") in (events[-1])
        assert ("Capabilities: docs-site, release\n") in (stdout.getvalue())

    def test_apply_keep_tokens_interactive_only_prompts_for_capabilities(
        self, mocker: MockerFixture
    ) -> None:
        confirm = mocker.patch("template_tool.cli.questionary.confirm")
        text = mocker.patch("template_tool.cli.questionary.text")
        self._init_target()
        confirm.side_effect = (
            mocker.Mock(ask=mocker.Mock(return_value=False)),
            mocker.Mock(ask=mocker.Mock(return_value=True)),
        )
        stdout = StringIO()

        with redirect_stdout(stdout):
            apply_main(
                [
                    str(self.target),
                    "--repo",
                    str(self.source),
                    "--ref",
                    "main",
                    "--template",
                    "example",
                    "--enable-capability",
                    "release",
                    "--interactive",
                    "--keep-tokens",
                ]
            )

        text.assert_not_called()
        assert (confirm.call_count) == (2)
        assert ("Capabilities: release\n") in (stdout.getvalue())
        assert ("{{PROJECT_NAME_JSON}}") in ((self.target / "project.toml").read_text())
        assert (self.target / "release.txt").is_file()

    def test_capability_discovery_text_and_json_do_not_require_or_mutate_repository(self) -> None:
        current = self.root / "current"
        current.mkdir()
        sentinel = current / "sentinel.txt"
        sentinel.write_text("unchanged\n", encoding="utf-8")
        commit = self._git(self.source, "rev-parse", "HEAD", capture=True)
        original_cwd = Path.cwd()
        text_output = StringIO()
        json_output = StringIO()
        try:
            os.chdir(current)
            with redirect_stdout(text_output):
                capabilities_main(
                    [
                        "--repo",
                        str(self.source),
                        "--ref",
                        "main",
                        "--template",
                        "example",
                    ]
                )
            with redirect_stdout(json_output):
                main(
                    [
                        "capabilities",
                        "--repo",
                        str(self.source),
                        "--ref",
                        "main",
                        "--template",
                        "example",
                        "--json",
                        "--source-checkout",
                        str(self.source),
                    ]
                )
        finally:
            os.chdir(original_cwd)

        assert (text_output.getvalue()) == (f"Repository: {self.source}\n"
            "Template: example\n"
            "Ref: main\n"
            f"Template-Commit: {commit}\n"
            "Capability: docs-site (default: disabled)\n"
            "Capability: release (default: disabled)\n")
        assert (json.loads(json_output.getvalue())) == ({
                "repository": str(self.source),
                "ref": "main",
                "commit": commit,
                "template": "example",
                "capabilities": [
                    {"name": "docs-site", "default_enabled": False},
                    {"name": "release", "default_enabled": False},
                ],
            })
        assert (tuple(current.iterdir())) == ((sentinel,))
        assert (sentinel.read_text(encoding="utf-8")) == ("unchanged\n")

    def test_capability_discovery_bootstrap_uses_selected_ref_engine(
        self, mocker: MockerFixture
    ) -> None:
        run_selected_engine = mocker.patch("template_tool.bootstrap._run_selected_engine")
        arguments = ["--ref", "main", "--template", "example", "--json"]

        bootstrap_capabilities_main(arguments)

        run_selected_engine.assert_called_once_with(
            "capabilities", arguments, capabilities_main
        )

    def test_umbrella_capability_discovery_uses_selected_ref_engine(
        self, mocker: MockerFixture
    ) -> None:
        run_selected_capabilities = mocker.patch(
            "template_tool.bootstrap.capabilities_main"
        )
        main(
            [
                "capabilities",
                "--repo",
                str(self.source),
                "--ref",
                "main",
                "--template",
                "example",
                "--json",
            ]
        )

        run_selected_capabilities.assert_called_once_with(
            [
                "--repo",
                str(self.source),
                "--ref",
                "main",
                "--template",
                "example",
                "--json",
            ]
        )

    def test_noninteractive_export_uses_defaults_overrides_and_capabilities(self) -> None:
        stdout = StringIO()

        with redirect_stdout(stdout):
            export_main(
                [
                    str(self.target),
                    "--repo",
                    str(self.source),
                    "--ref",
                    "main",
                    "--template",
                    "example",
                    "--project-name",
                    'CLI "Project"',
                    "--enable-capability",
                    "release",
                    "--source-checkout",
                    str(self.source),
                ]
            )

        assert ((self.target / "project.toml").read_text(encoding="utf-8")) == ('name = "CLI \\"Project\\""\nenabled = true\n')
        assert ((self.target / "cmd/replace-me-binary/main.txt").read_text(
                encoding="utf-8"
            )) == ('CLI "Project"\n')
        assert (self.target / "release.txt").is_file()
        assert not ((self.target / "docs.txt").exists())
        assert not ((self.target / ".git").exists())
        assert not ((self.target / "template-export.json").exists())
        for path in self.target.rglob("*"):
            assert not re.search(r"\{\{[A-Z]", str(path.relative_to(self.target)))
            if path.is_file():
                assert not re.search(r"\{\{[A-Z]", path.read_text(encoding="utf-8"))
        assert ("Capabilities: release\n") in (stdout.getvalue())
        assert (f"Destination: {self.target.resolve()}\n") in (stdout.getvalue())
        assert ("manual comparison and selective copying") in (stdout.getvalue())
        assert ("unbootstrapped") in (stdout.getvalue())

    def test_interactive_export_edits_every_metadata_value_and_confirms_summary(
        self, mocker: MockerFixture
    ) -> None:
        confirm = mocker.patch("template_tool.cli.questionary.confirm")
        text = mocker.patch("template_tool.cli.questionary.text")
        events: list[str] = []

        def confirm_prompt(message: str, *, default: bool):
            events.append(f"confirm:{message}")
            return mocker.Mock(ask=mocker.Mock(return_value=True))

        def text_prompt(message: str, *, default: str):
            events.append(f"text:{message}:{default}")
            value = 'Edited "Project"' if message == "Project Name" else default
            return mocker.Mock(ask=mocker.Mock(return_value=value))

        confirm.side_effect = confirm_prompt
        text.side_effect = text_prompt

        export_main(
            [
                str(self.target),
                "--repo",
                str(self.source),
                "--ref",
                "main",
                "--template",
                "example",
                "--project-name",
                "CLI Project",
                "--enable-capability",
                "release",
                "--interactive",
                "--source-checkout",
                str(self.source),
            ]
        )

        assert ([event.split(":", 1)[0] for event in events]) == (["confirm", "text", "text", "confirm"])
        assert ("docs-site") in (events[0])
        assert ("release") not in (events[0])
        assert ("Project Name:CLI Project") in (events[1])
        assert ("Binary Name:replace-me-binary") in (events[2])
        assert (f"Repository: {self.source}") in (events[-1])
        assert ("Template-Commit:") in (events[-1])
        assert ("Capabilities: docs-site, release") in (events[-1])
        assert (f"Destination: {self.target.resolve()}") in (events[-1])
        assert ((self.target / "cmd/replace-me-binary/main.txt").read_text(
                encoding="utf-8"
            )) == ('Edited "Project"\n')
        assert (self.target / "docs.txt").is_file()
        assert (self.target / "release.txt").is_file()

    def test_interactive_export_cancel_preserves_empty_destination(
        self, mocker: MockerFixture
    ) -> None:
        confirm = mocker.patch("template_tool.cli.questionary.confirm")
        text = mocker.patch("template_tool.cli.questionary.text")
        self.target.mkdir()
        text.side_effect = lambda message, *, default: mocker.Mock(
            ask=mocker.Mock(return_value=default)
        )
        confirm.return_value.ask.return_value = False

        with pytest.raises(SystemExit) as raised:
            export_main(
                [
                    str(self.target),
                    "--repo",
                    str(self.source),
                    "--ref",
                    "main",
                    "--template",
                    "example",
                    "--disable-capability",
                    "docs-site",
                    "--disable-capability",
                    "release",
                    "--interactive",
                    "--source-checkout",
                    str(self.source),
                ]
            )

        assert (raised.value.code) == (1)
        assert self.target.is_dir()
        assert (tuple(self.target.iterdir())) == (())

    def test_export_rejects_nonempty_destination_before_selection(self) -> None:
        self.target.mkdir()
        sentinel = self.target / "sentinel.txt"
        sentinel.write_text("unchanged\n", encoding="utf-8")
        stderr = StringIO()

        with redirect_stderr(stderr), pytest.raises(SystemExit) as raised:
            export_main(
                [
                    str(self.target),
                    "--repo",
                    str(self.source),
                    "--ref",
                    "main",
                    "--template",
                    "example",
                ]
            )

        assert (raised.value.code) == (1)
        assert ("not empty") in (stderr.getvalue())
        assert (sentinel.read_text(encoding="utf-8")) == ("unchanged\n")

    def test_export_instantiation_failure_preserves_empty_destination(self) -> None:
        self.target.mkdir()

        with pytest.raises(ApplicationError, match="missing required metadata"):
            export_template(
                str(self.source),
                "main",
                "example",
                self.target,
                {"project_name": "Incomplete"},
            )

        assert self.target.is_dir()
        assert (tuple(self.target.iterdir())) == (())

    def test_export_bootstrap_uses_selected_ref_engine(
        self, mocker: MockerFixture
    ) -> None:
        run_selected_engine = mocker.patch("template_tool.bootstrap._run_selected_engine")
        arguments = [str(self.target), "--ref", "main", "--template", "example"]

        bootstrap_export_main(arguments)

        run_selected_engine.assert_called_once_with("export", arguments, export_main)

    def test_umbrella_export_uses_selected_ref_engine(
        self, mocker: MockerFixture
    ) -> None:
        run_selected_export = mocker.patch("template_tool.bootstrap.export_main")
        main(
            [
                "export",
                str(self.target),
                "--repo",
                str(self.source),
                "--ref",
                "main",
                "--template",
                "example",
                "--enable-capability",
                "release",
            ]
        )

        run_selected_export.assert_called_once_with(
            [
                str(self.target),
                "--repo",
                str(self.source),
                "--ref",
                "main",
                "--template",
                "example",
                "--enable-capability",
                "release",
            ]
        )

    def test_init_cli_selects_non_default_capabilities_before_staging_template(
        self,
    ) -> None:
        workflow = self.source / "overlays/example/static/.github/workflows/ci.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("name: CI\n", encoding="utf-8")
        self._git(self.source, "add", "overlays/example/static/.github/workflows/ci.yml")
        self._git(self.source, "commit", "--quiet", "-m", "add nested template path")
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", str(self.target)],
            check=True,
        )
        self._configure_identity(self.target)
        stdout = StringIO()

        with redirect_stdout(stdout):
            init_main(
                [
                    str(self.target),
                    "--repo",
                    str(self.source),
                    "--ref",
                    "main",
                    "--template",
                    "example",
                    "--project-name",
                    "Initialized Project",
                    "--binary-name",
                    "initialized-project",
                    "--enable-capability",
                    "release",
                    "--enable-capability",
                    "docs-site",
                ]
            )

        output = stdout.getvalue()
        assert ("Initial-Commit:") in (output)
        assert ("Template-Commit:") in (output)
        assert ("Capabilities: docs-site, release") in (output)
        assert ("Protected project identity") not in (output)
        assert (self._git(self.target, "rev-list", "--parents", "-n", "1", "HEAD", capture=True)) == (self._git(self.target, "rev-parse", "HEAD", capture=True))
        assert (self._git(self.target, "diff", "--cached", "--name-only", capture=True)) == (".github/workflows/ci.yml\n.gitignore\nAGENTS.md\nLICENSE\ncmd/initialized-project/main.txt\ndocs.txt\nproject.toml\nrelease.txt")
        assert not (self._git(self.target, "ls-tree", "-r", "--name-only", "HEAD", capture=True))
        assert ("Initialized Project") in ((self.target / "project.toml").read_text())
        for protected in (".gitignore", "AGENTS.md", "LICENSE"):
            assert (self.target / protected).exists()
        assert not ((self.target / ".git/MERGE_HEAD").exists())

    def test_init_project_rejects_history_dirty_unborn_and_nested_target(self) -> None:
        self._init_target()
        with pytest.raises(ApplicationError, match="use apply-template"):
            initialize_project(str(self.source), "main", "example", self.target, {"project_name": "Example", "binary_name": "example"})

        dirty = self.root / "dirty"
        subprocess.run(["git", "init", "--quiet", str(dirty)], check=True)
        (dirty / "untracked.txt").write_text("dirty\n")
        with pytest.raises(ApplicationError, match="not clean"):
            initialize_project(str(self.source), "main", "example", dirty, {"project_name": "Example", "binary_name": "example"})

        unborn = self.root / "unborn"
        nested = unborn / "nested"
        nested.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(unborn)], check=True)
        with pytest.raises(ApplicationError, match="repository root"):
            initialize_project(str(self.source), "main", "example", nested, {"project_name": "Example", "binary_name": "example"})

    def test_init_project_validates_metadata_before_creating_initial_commit(self) -> None:
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", str(self.target)],
            check=True,
        )
        self._configure_identity(self.target)

        with pytest.raises(ApplicationError, match="missing required metadata: binary_name, project_name"):
            initialize_project(str(self.source), "main", "example", self.target, {})

        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=self.target,
            capture_output=True,
        )
        assert (completed.returncode) != (0)

    def test_init_project_keeps_target_unborn_when_source_preparation_fails(self) -> None:
        config = (self.source / "templates.toml").read_text(encoding="utf-8")
        (self.source / "templates.toml").write_text(
            config.replace(
                "[templates.example.capabilities]\n",
                "[templates.example.capabilities]\nDocs-Site = true\n",
            ),
            encoding="utf-8",
        )
        self._git(self.source, "add", "templates.toml")
        self._git(self.source, "commit", "--quiet", "-m", "break source contract")
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", str(self.target)],
            check=True,
        )
        self._configure_identity(self.target)

        with pytest.raises(ApplicationError, match="invalid capability name"):
            initialize_project(
                str(self.source),
                "main",
                "example",
                self.target,
                {"project_name": "Example", "binary_name": "example"},
            )

        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=self.target,
            capture_output=True,
        )
        assert (completed.returncode) != (0)
        assert not (self._git(self.target, "status", "--porcelain", capture=True))

    def test_init_interactive_cancel_keeps_repository_unborn(
        self, mocker: MockerFixture
    ) -> None:
        text = mocker.patch("template_tool.cli.questionary.text")
        confirm = mocker.patch("template_tool.cli.questionary.confirm")
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", str(self.target)],
            check=True,
        )
        self._configure_identity(self.target)
        text.return_value.ask.return_value = "Interactive Project"
        confirm.return_value.ask.return_value = False

        with pytest.raises(SystemExit) as exit_context:
            init_main(
                [
                    str(self.target),
                    "--repo",
                    str(self.source),
                    "--ref",
                    "main",
                    "--template",
                    "example",
                    "--interactive",
                ]
            )

        assert (exit_context.value.code) == (1)
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=self.target,
            capture_output=True,
        )
        assert (completed.returncode) != (0)
        assert not (self._git(self.target, "status", "--porcelain", capture=True))
