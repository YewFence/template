from __future__ import annotations

import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from template_tool.application import (
    ApplicationError,
    apply_template,
    initialize_project,
)
from template_tool.cli import apply_main, init_main


class ApplyTemplateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source"
        self.target = self.root / "target"
        self._init_source()

    def tearDown(self) -> None:
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
        (self.source / "templates/example").mkdir(parents=True)
        (self.source / "tools/template-tool/README").write_text("tool\n")
        (self.source / "scripts/apply-template").write_text("launcher\n")
        (self.source / "templates.toml").write_text(
            "version = 1\n"
            "[apply]\n"
            'protected = [".gitignore", "AGENTS.*", "LICENSE*"]\n'
            'hints = ["Review protected files manually."]\n'
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
            'binary_name = "validation-project"\n',
            encoding="utf-8",
        )
        (self.source / "templates/example/.gitignore").write_text("template-cache/\n")
        (self.source / "templates/example/AGENTS.md").write_text("template agents\n")
        (self.source / "templates/example/LICENSE").write_text("template license\n")
        (self.source / "templates/example/project.toml").write_text(
            'name = {{PROJECT_NAME_JSON}}\nenabled = true\n'
        )
        command = self.source / "templates/example/cmd/{{BINARY_NAME}}/main.txt"
        command.parent.mkdir(parents=True)
        command.write_text("{{PROJECT_NAME}}\n", encoding="utf-8")
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

        self.assertFalse(result.conflicted)
        self.assertTrue(result.jujutsu)
        self.assertEqual(result.hints, ("Review protected files manually.",))
        self.assertEqual(
            result.skipped, (".gitignore", "AGENTS.md", "LICENSE")
        )
        self.assertEqual((self.target / ".gitignore").read_text(), ".jj/\ntarget-cache/\n")
        self.assertEqual((self.target / "AGENTS.md").read_text(), "target agents\n")
        self.assertEqual((self.target / "LICENSE").read_text(), "target license\n")
        self.assertEqual(
            (self.target / "project.toml").read_text(),
            'name = {{PROJECT_NAME_JSON}}\nenabled = true\n',
        )
        self.assertEqual(
            self._git(self.target, "diff", "--cached", "--name-only", capture=True),
            "cmd/{{BINARY_NAME}}/main.txt\nproject.toml",
        )
        self.assertEqual(self._git(self.target, "rev-parse", "HEAD", capture=True), head)
        self.assertFalse((self.target / ".git/MERGE_HEAD").exists())

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

        self.assertTrue(result.instantiated)
        self.assertEqual(
            (self.target / "project.toml").read_text(),
            'name = "Applied \\"Project\\""\nenabled = true\n',
        )
        self.assertEqual(
            (self.target / "cmd/applied-project/main.txt").read_text(),
            'Applied "Project"\n',
        )
        self.assertEqual(
            self._git(self.target, "diff", "--cached", "--name-only", capture=True),
            "cmd/applied-project/main.txt\nproject.toml",
        )

    def test_apply_requires_complete_metadata_unless_keep_tokens(self) -> None:
        self._init_target()

        with self.assertRaisesRegex(
            ApplicationError, "missing required metadata: binary_name, project_name"
        ):
            apply_template(
                str(self.source),
                "main",
                "example",
                self.target,
                metadata={},
                keep_tokens=False,
            )

    def test_conflict_preserves_index_can_be_cancelled_and_resolved(self) -> None:
        (self.source / "templates/example/README.md").write_text("template\n")
        self._git(self.source, "add", "templates/example/README.md")
        self._git(self.source, "commit", "--quiet", "-m", "add template readme")
        head = self._init_target({"README.md": "target\n"})

        result = apply_template(
            str(self.source), "main", "example", self.target, keep_tokens=True
        )

        self.assertTrue(result.conflicted)
        self.assertTrue(self._git(self.target, "ls-files", "-u", capture=True))
        self.assertFalse((self.target / ".git/MERGE_HEAD").exists())
        self._git(self.target, "reset", "--hard", "HEAD")
        self.assertFalse(self._git(self.target, "status", "--porcelain", capture=True))
        self.assertEqual(self._git(self.target, "rev-parse", "HEAD", capture=True), head)

        result = apply_template(
            str(self.source), "main", "example", self.target, keep_tokens=True
        )
        self.assertTrue(result.conflicted)
        (self.target / "README.md").write_text("resolved\n")
        self._git(self.target, "add", "README.md")
        self._git(self.target, "commit", "--quiet", "-m", "apply template")
        parents = self._git(
            self.target, "rev-list", "--parents", "-n", "1", "HEAD", capture=True
        ).split()
        self.assertEqual(len(parents), 2)

    def test_dirty_unborn_and_in_progress_repositories_are_rejected(self) -> None:
        self._init_target()
        (self.target / "dirty.txt").write_text("dirty\n")
        with self.assertRaisesRegex(ApplicationError, "not clean"):
            apply_template(
                str(self.source), "main", "example", self.target, keep_tokens=True
            )

        unborn = self.root / "unborn"
        subprocess.run(["git", "init", "--quiet", str(unborn)], check=True)
        with self.assertRaisesRegex(ApplicationError, "at least one commit"):
            apply_template(
                str(self.source), "main", "example", unborn, keep_tokens=True
            )

        (self.target / "dirty.txt").unlink()
        (self.target / ".git/REVERT_HEAD").write_text("marker\n")
        with self.assertRaisesRegex(ApplicationError, "REVERT_HEAD"):
            apply_template(
                str(self.source), "main", "example", self.target, keep_tokens=True
            )

    @mock.patch("template_tool.cli._collect_metadata")
    def test_cli_rejects_dirty_repository_before_interactive_metadata(
        self, collect_metadata: mock.Mock
    ) -> None:
        self._init_target()
        (self.target / "dirty.txt").write_text("dirty\n")
        collect_metadata.return_value = {
            "project_name": "Example",
            "binary_name": "example",
        }
        stderr = StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as exit_context:
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

        self.assertEqual(exit_context.exception.code, 1)
        self.assertIn("target repository is not clean", stderr.getvalue())
        collect_metadata.assert_not_called()

    def test_cli_returns_nonzero_and_prints_conflict_recovery_hints(self) -> None:
        (self.source / "templates/example/README.md").write_text("template\n")
        self._git(self.source, "add", "templates/example/README.md")
        self._git(self.source, "commit", "--quiet", "-m", "add template readme")
        self._init_target({"README.md": "target\n"})
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exit_context:
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
                    ]
                )

        self.assertEqual(exit_context.exception.code, 1)
        self.assertIn("Template-Commit:", stdout.getvalue())
        self.assertIn("git status", stdout.getvalue())
        self.assertIn("git diff --check", stdout.getvalue())
        self.assertIn("git reset --hard HEAD", stdout.getvalue())
        self.assertFalse((self.target / ".git/MERGE_HEAD").exists())

    def test_cli_rejects_keep_tokens_with_metadata(self) -> None:
        self._init_target()
        stderr = StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as exit_context:
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

        self.assertEqual(exit_context.exception.code, 1)
        self.assertIn("cannot be combined", stderr.getvalue())
        self.assertFalse(self._git(self.target, "status", "--porcelain", capture=True))

    def test_init_project_creates_initial_commit_and_stages_template(self) -> None:
        workflow = self.source / "templates/example/.github/workflows/ci.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("name: CI\n", encoding="utf-8")
        self._git(self.source, "add", "templates/example/.github/workflows/ci.yml")
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
                ]
            )

        output = stdout.getvalue()
        self.assertIn("Initial-Commit:", output)
        self.assertIn("Template-Commit:", output)
        self.assertNotIn("Protected project identity", output)
        self.assertEqual(
            self._git(self.target, "rev-list", "--parents", "-n", "1", "HEAD", capture=True),
            self._git(self.target, "rev-parse", "HEAD", capture=True),
        )
        self.assertEqual(
            self._git(self.target, "diff", "--cached", "--name-only", capture=True),
            ".github/workflows/ci.yml\n.gitignore\nAGENTS.md\nLICENSE\ncmd/initialized-project/main.txt\nproject.toml",
        )
        self.assertIn("Initialized Project", (self.target / "project.toml").read_text())
        for protected in (".gitignore", "AGENTS.md", "LICENSE"):
            self.assertTrue((self.target / protected).exists())
        self.assertFalse((self.target / ".git/MERGE_HEAD").exists())

    def test_init_project_rejects_history_dirty_unborn_and_nested_target(self) -> None:
        self._init_target()
        with self.assertRaisesRegex(ApplicationError, "use apply-template"):
            initialize_project(str(self.source), "main", "example", self.target, {"project_name": "Example", "binary_name": "example"})

        dirty = self.root / "dirty"
        subprocess.run(["git", "init", "--quiet", str(dirty)], check=True)
        (dirty / "untracked.txt").write_text("dirty\n")
        with self.assertRaisesRegex(ApplicationError, "not clean"):
            initialize_project(str(self.source), "main", "example", dirty, {"project_name": "Example", "binary_name": "example"})

        unborn = self.root / "unborn"
        nested = unborn / "nested"
        nested.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(unborn)], check=True)
        with self.assertRaisesRegex(ApplicationError, "repository root"):
            initialize_project(str(self.source), "main", "example", nested, {"project_name": "Example", "binary_name": "example"})

    def test_init_project_validates_metadata_before_creating_initial_commit(self) -> None:
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", str(self.target)],
            check=True,
        )
        self._configure_identity(self.target)

        with self.assertRaisesRegex(
            ApplicationError, "missing required metadata: binary_name, project_name"
        ):
            initialize_project(str(self.source), "main", "example", self.target, {})

        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=self.target,
            capture_output=True,
        )
        self.assertNotEqual(completed.returncode, 0)

    @mock.patch("template_tool.cli.questionary.confirm")
    @mock.patch("template_tool.cli.questionary.text")
    def test_init_interactive_cancel_keeps_repository_unborn(
        self, text: mock.Mock, confirm: mock.Mock
    ) -> None:
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", str(self.target)],
            check=True,
        )
        self._configure_identity(self.target)
        text.return_value.ask.return_value = "Interactive Project"
        confirm.return_value.ask.return_value = False

        with self.assertRaises(SystemExit) as exit_context:
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

        self.assertEqual(exit_context.exception.code, 1)
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=self.target,
            capture_output=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(self._git(self.target, "status", "--porcelain", capture=True))


if __name__ == "__main__":
    unittest.main()
