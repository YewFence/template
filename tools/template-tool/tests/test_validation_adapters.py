from __future__ import annotations

import subprocess

import pytest

from staging_harness import REPOSITORY_ROOT, AdapterFailure, StagingHarness


class TestValidationAdapter(StagingHarness):
    def test_common_namespaced_task_is_discoverable(self) -> None:
        completed = subprocess.run(
            ["mise", "run", "//overlays/common:check", "--help"],
            cwd=REPOSITORY_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        assert "Usage: //overlays/common:check <template_root>" in completed.stdout

    def test_python_namespaced_task_is_discoverable(self) -> None:
        completed = subprocess.run(
            ["mise", "run", "//overlays/python:check", "--help"],
            cwd=REPOSITORY_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        assert "Usage: //overlays/python:check <template_root>" in completed.stdout

    def test_go_cli_namespaced_task_is_discoverable(self) -> None:
        completed = subprocess.run(
            ["mise", "run", "//overlays/go-cli:check", "--help"],
            cwd=REPOSITORY_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        assert "Usage: //overlays/go-cli:check <template_root>" in completed.stdout

    def test_rust_namespaced_task_is_discoverable(self) -> None:
        completed = subprocess.run(
            ["mise", "run", "//overlays/rust:check", "--help"],
            cwd=REPOSITORY_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        assert "Usage: //overlays/rust:check <template_root>" in completed.stdout

    def test_common_adapter_runs_through_namespaced_mise_task(self) -> None:
        with self.staged_repository("common", ()) as root:
            completed = self.invoke_adapter(
                root,
                "common",
                (),
                (),
                task_name="//overlays/common:check",
            )
            assert completed.returncode == 0, completed.stderr
            calls = (root / "mise-calls").read_text(encoding="utf-8").splitlines()
            assert "run check" in calls

    @pytest.mark.parametrize("profile", ("common", "python", "go-cli", "rust"))
    def test_docs_site_disabled_skips_documentation_toolchain(self, profile: str) -> None:
        calls = self.run_adapter(profile, ())

        assert "run docs:lock" not in calls
        assert "run docs:build" not in calls

    @pytest.mark.parametrize("profile", ("common", "python", "go-cli", "rust"))
    def test_docs_site_enabled_locks_and_builds_documentation(self, profile: str) -> None:
        calls = self.run_adapter(profile, ("docs-site",))

        assert "run docs:lock" in calls
        assert "run docs:build" in calls

    def test_crates_io_publish_enabled_checks_package(self) -> None:
        calls = self.run_adapter("rust", ("crates-io-publish",))

        assert "run crates-io:package:check" in calls

    def test_crates_io_publish_disabled_skips_package_check(self) -> None:
        calls = self.run_adapter("rust", ())

        assert "run crates-io:package:check" not in calls

    def test_container_image_publish_enabled_builds_local_image(self) -> None:
        calls = self.run_adapter("go-cli", ("container-image-publish",))

        assert "run container:build" in calls

    def test_container_image_publish_disabled_skips_local_image(self) -> None:
        calls = self.run_adapter("go-cli", ())

        assert "run container:build" not in calls

    @pytest.mark.parametrize("profile", ("common", "python", "go-cli", "rust"))
    def test_codecov_upload_enabled_validates_both_workflows(self, profile: str) -> None:
        calls = self.run_adapter(profile, ("codecov-upload",))
        assert "run actions:update" in calls

    @pytest.mark.parametrize("profile", ("common", "python", "go-cli", "rust"))
    def test_codecov_upload_disabled_skips_coverage_validation(self, profile: str) -> None:
        calls = self.run_adapter(profile, ())
        assert "run coverage" not in calls

    def test_common_codecov_upload_requires_coverage_placeholder_contract(self) -> None:
        with self.staged_repository("common", ("codecov-upload",)) as root:
            mise_path = root / "template" / "mise.toml"
            mise_path.write_text(
                mise_path.read_text(encoding="utf-8").replace("exit 1", "exit 0"),
                encoding="utf-8",
            )
            completed = self.invoke_adapter(
                root,
                "common",
                ("codecov-upload",),
                ("codecov-upload",),
            )
            assert completed.returncode != 0
            assert "coverage placeholder contract is incomplete" in completed.stderr

    def test_python_codecov_upload_requires_coverage_dependency(self) -> None:
        with self.staged_repository("python", ("codecov-upload",)) as root:
            pyproject = root / "template" / "pyproject.toml"
            pyproject.write_text(
                pyproject.read_text(encoding="utf-8").replace(
                    'coverage = ["pytest-cov>=7,<8"]\n', ""
                ),
                encoding="utf-8",
            )
            completed = self.invoke_adapter(
                root, "python", ("codecov-upload",), ("codecov-upload",)
            )
            assert completed.returncode != 0
            assert "coverage dependency does not match codecov-upload" in completed.stderr

    def test_explicit_docs_site_state_rejects_mismatched_staged_project(self) -> None:
        with pytest.raises(AdapterFailure) as captured:
            self.run_adapter("common", ("docs-site",), staged_capabilities=())
        assert "docs-site" in captured.value.stderr

    def test_explicit_crates_io_state_rejects_mismatched_staged_project(self) -> None:
        with pytest.raises(AdapterFailure) as captured:
            self.run_adapter(
                "rust",
                ("crates-io-publish",),
                staged_capabilities=(),
            )
        assert "crates-io-publish" in captured.value.stderr

    def test_explicit_container_image_state_rejects_mismatched_staged_project(
        self,
    ) -> None:
        with pytest.raises(AdapterFailure) as captured:
            self.run_adapter(
                "go-cli",
                ("container-image-publish",),
                staged_capabilities=(),
            )
        assert "container-image-publish" in captured.value.stderr

    @pytest.mark.parametrize("profile", ("common", "python", "go-cli", "rust"))
    def test_explicit_codecov_upload_state_rejects_mismatched_staged_project(
        self,
        profile: str,
    ) -> None:
        with pytest.raises(AdapterFailure) as captured:
            self.run_adapter(profile, ("codecov-upload",), staged_capabilities=())
        assert captured.value.profile == profile
        assert "codecov-upload" in captured.value.stderr

    def test_adapter_reports_duplicate_capability_input(self) -> None:
        with self.staged_repository("common", ("docs-site",)) as root:
            environment = self.environment_for(root, "common", ("docs-site",), ("docs-site",))
            environment["TEMPLATE_TOOL_ENABLED_CAPABILITIES"] = '["docs-site","docs-site"]'
            completed = self.invoke_adapter(
                root,
                "common",
                ("docs-site",),
                ("docs-site",),
                environment=environment,
            )
            assert completed.returncode != 0
            assert "duplicates" in completed.stderr

    def test_adapter_reports_unknown_capability_input(self) -> None:
        with self.staged_repository("common", ()) as root:
            environment = self.environment_for(root, "common", (), ())
            environment["TEMPLATE_TOOL_ENABLED_CAPABILITIES"] = '["docs-site","unknown-capability"]'
            completed = self.invoke_adapter(
                root,
                "common",
                (),
                (),
                environment=environment,
            )
            assert completed.returncode != 0
            assert "unexpected capabilities: unknown-capability" in completed.stderr
