from __future__ import annotations

from pathlib import Path

import pytest

from staging_harness import StagingHarness, capability_environment
from template_tool.staging_validation import (
    StagingContext,
    ValidationError,
    parse_enabled_capabilities,
    validate_codecov_upload,
    validate_docs_site,
)


def test_parse_enabled_capabilities_returns_canonical_allowed_set() -> None:
    assert parse_enabled_capabilities(
        '["docs-site","codecov-upload"]',
        allowed=("codecov-upload", "docs-site"),
    ) == ("codecov-upload", "docs-site")


@pytest.mark.parametrize(
    ("value", "message"),
    (
        ("not-json", "JSON array"),
        ("{}", "JSON array"),
        ('["unknown"]', "unexpected capabilities"),
        ('["docs-site","docs-site"]', "duplicates"),
    ),
)
def test_parse_enabled_capabilities_rejects_invalid_input(value: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse_enabled_capabilities(value, allowed=("docs-site",))


def test_parse_enabled_capabilities_requires_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEMPLATE_TOOL_ENABLED_CAPABILITIES", raising=False)
    with pytest.raises(ValidationError, match="TEMPLATE_TOOL_ENABLED_CAPABILITIES is required"):
        parse_enabled_capabilities(allowed=("docs-site",))


class TestStagingContext:
    def setup_method(self) -> None:
        self.harness = StagingHarness()

    def _context(self, root: Path, capabilities: tuple[str, ...]) -> StagingContext:
        return StagingContext(
            root / "template",
            capabilities,
            self.harness.environment_for(root, "common", capabilities, capabilities),
        )

    def test_from_environment_rejects_non_directory_root(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv(
            "TEMPLATE_TOOL_ENABLED_CAPABILITIES",
            capability_environment(("docs-site",)),
        )
        with pytest.raises(ValidationError, match="not a directory"):
            StagingContext.from_environment(
                tmp_path / "missing",
                allowed_capabilities=("docs-site",),
            )

    def test_from_environment_rejects_missing_capability_environment(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.delenv("TEMPLATE_TOOL_ENABLED_CAPABILITIES", raising=False)
        with pytest.raises(ValidationError, match="is required"):
            StagingContext.from_environment(
                tmp_path,
                allowed_capabilities=("docs-site",),
            )

    def test_from_environment_rejects_unknown_capability(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv(
            "TEMPLATE_TOOL_ENABLED_CAPABILITIES",
            '["unknown-capability"]',
        )
        with pytest.raises(ValidationError, match="unexpected capabilities: unknown-capability"):
            StagingContext.from_environment(
                tmp_path,
                allowed_capabilities=("docs-site",),
            )

    def test_capability_helpers_and_environment_overrides(self) -> None:
        with self.harness.staged_repository("common", ("docs-site",)) as root:
            context = self._context(root, ("docs-site",))
            assert context.has_capability("docs-site")
            assert not context.has_capability("codecov-upload")
            assert context.enabled_capabilities == ("docs-site",)

            overridden = context.with_environment(TEMPLATE_TOOL_TEST_MARKER="set")
            assert overridden.environment["TEMPLATE_TOOL_TEST_MARKER"] == "set"
            assert "TEMPLATE_TOOL_TEST_MARKER" not in context.environment

            removed = overridden.with_environment(TEMPLATE_TOOL_TEST_MARKER=None)
            assert "TEMPLATE_TOOL_TEST_MARKER" not in removed.environment

    def test_filesystem_helpers_and_read_errors(self) -> None:
        with self.harness.staged_repository("common", ()) as root:
            context = self._context(root, ())
            assert context.exists("tracked")
            assert not context.exists("absent")
            assert context.read("tracked") == "tracked\n"
            with pytest.raises(ValidationError, match="required file is not readable: absent"):
                context.read("absent")

    def test_assert_tasks_accepts_available_and_rejects_missing(self) -> None:
        with self.harness.staged_repository("common", ()) as root:
            context = self._context(root, ())
            context.assert_tasks(("check", "deps:update"), message="probe")
            with pytest.raises(ValidationError, match="probe: coverage"):
                context.assert_tasks(("coverage",), message="probe")
            context.assert_tasks(("check",), message="probe", ci=True)

    def test_assert_tool_accepts_available_and_rejects_missing(self) -> None:
        with self.harness.staged_repository("common", ()) as root:
            context = self._context(root, ())
            context.assert_tool("python", message="probe")
            with pytest.raises(ValidationError, match="probe: node"):
                context.assert_tool("node", message="probe")

    def test_assert_contains_and_assert_absent(self) -> None:
        with self.harness.staged_repository("common", ()) as root:
            context = self._context(root, ())
            context.assert_contains("tracked", ("tracked",), message="probe")
            with pytest.raises(ValidationError, match="probe: missing"):
                context.assert_contains("tracked", ("missing",), message="probe")
            context.assert_absent("absent", message="probe")
            with pytest.raises(ValidationError, match="probe"):
                context.assert_absent("tracked", message="probe")


class TestValidateDocsSite:
    """Direct tests for the shared docs-site contract, staged once via the harness."""

    def setup_method(self) -> None:
        self.harness = StagingHarness()

    def _context(self, root: Path, capabilities: tuple[str, ...]) -> StagingContext:
        return StagingContext(
            root / "template",
            capabilities,
            self.harness.environment_for(root, "common", capabilities, capabilities),
        )

    def test_enabled_accepts_complete_docs_outputs(self) -> None:
        with self.harness.staged_repository("common", ("docs-site",)) as root:
            validate_docs_site(self._context(root, ("docs-site",)))

    def test_enabled_rejects_missing_docs_workflow(self) -> None:
        with self.harness.staged_repository("common", ("docs-site",)) as root:
            (root / "template/.github/workflows/docs.yml").unlink()
            with pytest.raises(ValidationError, match="complete outputs are missing"):
                validate_docs_site(self._context(root, ("docs-site",)))

    def test_enabled_rejects_missing_docs_task(self) -> None:
        with self.harness.staged_repository("common", ("docs-site",)) as root:
            environment = self.harness.environment_for(
                root, "common", ("docs-site",), ("docs-site",)
            )
            environment["MISE_TASKS"] = environment["MISE_TASKS"].replace("docs:build", "")
            context = StagingContext(root / "template", ("docs-site",), environment)
            with pytest.raises(ValidationError, match="mise task is missing: docs:build"):
                validate_docs_site(context)

    def test_enabled_rejects_missing_docs_tool(self) -> None:
        with self.harness.staged_repository("common", ("docs-site",)) as root:
            (root / "template/mise.toml").write_text('[tools]\npython = "3.14"\n', encoding="utf-8")
            with pytest.raises(ValidationError, match="mise tool is missing: node"):
                validate_docs_site(self._context(root, ("docs-site",)))

    def test_enabled_rejects_missing_ci_docs_job(self) -> None:
        with self.harness.staged_repository("common", ("docs-site",)) as root:
            ci_path = root / "template/.github/workflows/ci.yml"
            ci_path.write_text(
                ci_path.read_text(encoding="utf-8").replace("  docs:", "  pages:"),
                encoding="utf-8",
            )
            with pytest.raises(ValidationError, match="CI docs job is missing"):
                validate_docs_site(self._context(root, ("docs-site",)))

    def test_disabled_accepts_clean_project(self) -> None:
        with self.harness.staged_repository("common", ()) as root:
            validate_docs_site(self._context(root, ()))

    def test_disabled_rejects_leftover_docs_outputs(self) -> None:
        with self.harness.staged_repository("common", ()) as root:
            (root / "template/docs").mkdir()
            with pytest.raises(ValidationError, match="complete outputs remain"):
                validate_docs_site(self._context(root, ()))

    def test_disabled_rejects_leftover_docs_tasks(self) -> None:
        with self.harness.staged_repository("common", ()) as root:
            environment = self.harness.environment_for(root, "common", (), ())
            environment["MISE_TASKS"] += "\ndocs:dev"
            context = StagingContext(root / "template", (), environment)
            with pytest.raises(ValidationError, match="mise docs tasks remain"):
                validate_docs_site(context)


class TestValidateCodecovUpload:
    """Direct tests for the shared Codecov contract, staged once via the harness."""

    def setup_method(self) -> None:
        self.harness = StagingHarness()

    def _context(self, root: Path, capabilities: tuple[str, ...]) -> StagingContext:
        return StagingContext(
            root / "template",
            capabilities,
            self.harness.environment_for(root, "common", capabilities, capabilities),
        )

    def test_enabled_accepts_complete_contract(self) -> None:
        with self.harness.staged_repository("common", ("codecov-upload",)) as root:
            validate_codecov_upload(
                self._context(root, ("codecov-upload",)),
                coverage_report="coverage.xml",
                coverage_placeholder=(
                    "[tasks.coverage]",
                    "generates coverage.xml in the repository root",
                    "exit 1",
                ),
                forbidden_coverage_tools=(r"cargo-llvm-cov", r"golang\.org/.*/cover"),
                required_ci_tools=('"pipx:codecov-cli" = "11"',),
            )

    def test_enabled_rejects_missing_default_branch_workflow(self) -> None:
        with self.harness.staged_repository("common", ("codecov-upload",)) as root:
            (root / "template/.github/workflows/coverage.yml").unlink()
            with pytest.raises(ValidationError, match="default branch workflow is missing"):
                validate_codecov_upload(
                    self._context(root, ("codecov-upload",)),
                    coverage_report="coverage.xml",
                    coverage_placeholder=(
                        "[tasks.coverage]",
                        "generates coverage.xml in the repository root",
                        "exit 1",
                    ),
                )

    def test_enabled_rejects_unsafe_ci_permissions(self) -> None:
        with self.harness.staged_repository("common", ("codecov-upload",)) as root:
            ci_path = root / "template/.github/workflows/ci.yml"
            ci_path.write_text(
                ci_path.read_text(encoding="utf-8").replace(
                    "      contents: read", "      contents: read\n        id-token: write"
                ),
                encoding="utf-8",
            )
            with pytest.raises(ValidationError, match="unsafe permissions or authentication"):
                validate_codecov_upload(
                    self._context(root, ("codecov-upload",)),
                    coverage_report="coverage.xml",
                    coverage_placeholder=(
                        "[tasks.coverage]",
                        "generates coverage.xml in the repository root",
                        "exit 1",
                    ),
                )

    def test_enabled_rejects_unignored_coverage_report(self) -> None:
        with self.harness.staged_repository("common", ("codecov-upload",)) as root:
            (root / "template/.gitignore").write_text("", encoding="utf-8")
            with pytest.raises(ValidationError, match="not ignored: coverage.xml"):
                validate_codecov_upload(
                    self._context(root, ("codecov-upload",)),
                    coverage_report="coverage.xml",
                    coverage_placeholder=(
                        "[tasks.coverage]",
                        "generates coverage.xml in the repository root",
                        "exit 1",
                    ),
                )

    def test_enabled_rejects_forbidden_coverage_tools(self) -> None:
        with self.harness.staged_repository("common", ("codecov-upload",)) as root:
            ci_tools_path = root / "template/mise.ci.toml"
            ci_tools_path.write_text(
                ci_tools_path.read_text(encoding="utf-8") + '"cargo:cargo-llvm-cov" = "0.8"\n',
                encoding="utf-8",
            )
            with pytest.raises(ValidationError, match="coverage tool ownership is incorrect"):
                validate_codecov_upload(
                    self._context(root, ("codecov-upload",)),
                    coverage_report="coverage.xml",
                    coverage_placeholder=(
                        "[tasks.coverage]",
                        "generates coverage.xml in the repository root",
                        "exit 1",
                    ),
                    forbidden_coverage_tools=(r"cargo-llvm-cov",),
                )

    def test_enabled_rejects_codecov_cli_in_main_tool_file(self) -> None:
        with self.harness.staged_repository("common", ("codecov-upload",)) as root:
            mise_path = root / "template/mise.toml"
            mise_path.write_text(
                mise_path.read_text(encoding="utf-8") + '"pipx:codecov-cli" = "11"\n',
                encoding="utf-8",
            )
            with pytest.raises(ValidationError, match="CLI tool ownership is incorrect"):
                validate_codecov_upload(
                    self._context(root, ("codecov-upload",)),
                    coverage_report="coverage.xml",
                    coverage_placeholder=(
                        "[tasks.coverage]",
                        "generates coverage.xml in the repository root",
                        "exit 1",
                    ),
                    required_ci_tools=('"pipx:codecov-cli" = "11"',),
                )

    def test_enabled_rejects_incomplete_placeholder_contract(self) -> None:
        with self.harness.staged_repository("common", ("codecov-upload",)) as root:
            mise_path = root / "template/mise.toml"
            mise_path.write_text(
                mise_path.read_text(encoding="utf-8").replace("exit 1", "exit 0"),
                encoding="utf-8",
            )
            with pytest.raises(ValidationError, match="coverage placeholder contract is incomplete"):
                validate_codecov_upload(
                    self._context(root, ("codecov-upload",)),
                    coverage_report="coverage.xml",
                    coverage_placeholder=(
                        "[tasks.coverage]",
                        "generates coverage.xml in the repository root",
                        "exit 1",
                    ),
                )

    def test_disabled_accepts_clean_project(self) -> None:
        with self.harness.staged_repository("common", ()) as root:
            validate_codecov_upload(
                self._context(root, ()),
                coverage_report="coverage.xml",
            )

    def test_disabled_rejects_leftover_coverage_workflow(self) -> None:
        with self.harness.staged_repository("common", ()) as root:
            workflows = root / "template/.github/workflows"
            (workflows / "coverage.yml").write_text("name: Coverage\n", encoding="utf-8")
            with pytest.raises(ValidationError, match="coverage behavior remains"):
                validate_codecov_upload(
                    self._context(root, ()),
                    coverage_report="coverage.xml",
                )
