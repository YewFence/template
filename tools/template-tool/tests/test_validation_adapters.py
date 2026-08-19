from __future__ import annotations

import json
import os
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]


class ValidationAdapterTest(unittest.TestCase):
    def test_docs_site_disabled_skips_documentation_toolchain(self) -> None:
        for profile in ("common", "go-cli", "rust"):
            with self.subTest(profile=profile):
                calls = self.run_adapter(profile, ())

                self.assertNotIn("run docs:lock", calls)
                self.assertNotIn("run docs:build", calls)

    def test_docs_site_enabled_locks_and_builds_documentation(self) -> None:
        for profile in ("common", "go-cli", "rust"):
            with self.subTest(profile=profile):
                calls = self.run_adapter(profile, ("docs-site",))

                self.assertIn("run docs:lock", calls)
                self.assertIn("run docs:build", calls)

    def test_crates_io_publish_enabled_checks_package(self) -> None:
        calls = self.run_adapter("rust", ("crates-io-publish",))

        self.assertIn("run crates-io:package:check", calls)

    def test_crates_io_publish_disabled_skips_package_check(self) -> None:
        calls = self.run_adapter("rust", ())

        self.assertNotIn("run crates-io:package:check", calls)

    def test_container_image_publish_enabled_builds_local_image(self) -> None:
        calls = self.run_adapter("go-cli", ("container-image-publish",))

        self.assertIn("run container:build", calls)

    def test_container_image_publish_disabled_skips_local_image(self) -> None:
        calls = self.run_adapter("go-cli", ())

        self.assertNotIn("run container:build", calls)

    def test_codecov_upload_enabled_validates_both_workflows(self) -> None:
        for profile in ("common", "go-cli", "rust"):
            with self.subTest(profile=profile):
                calls = self.run_adapter(profile, ("codecov-upload",))
                self.assertIn("run actions:update", calls)

    def test_codecov_upload_disabled_skips_coverage_validation(self) -> None:
        for profile in ("common", "go-cli", "rust"):
            with self.subTest(profile=profile):
                calls = self.run_adapter(profile, ())
                self.assertNotIn("run coverage", calls)

    def test_explicit_docs_site_state_rejects_mismatched_staged_project(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_adapter("common", ("docs-site",), staged_capabilities=())

    def test_explicit_crates_io_state_rejects_mismatched_staged_project(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_adapter(
                "rust",
                ("crates-io-publish",),
                staged_capabilities=(),
            )

    def test_explicit_container_image_state_rejects_mismatched_staged_project(
        self,
    ) -> None:
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_adapter(
                "go-cli",
                ("container-image-publish",),
                staged_capabilities=(),
            )

    def run_adapter(
        self,
        profile: str,
        enabled_capabilities: tuple[str, ...],
        *,
        staged_capabilities: tuple[str, ...] | None = None,
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            template_root = temporary_root / "template"
            template_root.mkdir()
            if staged_capabilities is None:
                staged_capabilities = enabled_capabilities
            self.write_staged_project(template_root, profile, staged_capabilities)
            self.initialize_repository(template_root)

            binary_directory = temporary_root / "bin"
            binary_directory.mkdir()
            calls_path = temporary_root / "mise-calls"
            shim_environment = self.write_mise_shim(
                binary_directory / "mise",
                calls_path,
                profile,
                staged_capabilities,
            )

            config = tomllib.loads(
                (REPOSITORY_ROOT / "overlays" / profile / "mise.toml").read_text(
                    encoding="utf-8"
                )
            )
            script = config["tasks"]["check"]["run"].replace(
                '"{{ usage.template_root }}"', f'"{template_root}"'
            )
            environment = os.environ | {
                "PATH": f"{binary_directory}:{os.environ['PATH']}",
                "TEMPLATE_TOOL_ENABLED_CAPABILITIES": json.dumps(
                    enabled_capabilities, separators=(",", ":")
                ),
            } | shim_environment

            subprocess.run(
                ["/bin/bash", "-eu", "-c", script],
                cwd=REPOSITORY_ROOT / "overlays" / profile,
                env=environment,
                check=True,
                text=True,
                capture_output=True,
            )
            return calls_path.read_text(encoding="utf-8").splitlines()

    def write_staged_project(
        self,
        template_root: Path,
        profile: str,
        enabled_capabilities: tuple[str, ...],
    ) -> None:
        docs_enabled = "docs-site" in enabled_capabilities
        crates_io_enabled = "crates-io-publish" in enabled_capabilities
        container_image_enabled = "container-image-publish" in enabled_capabilities
        codecov_enabled = "codecov-upload" in enabled_capabilities
        (template_root / ".github/workflows").mkdir(parents=True)
        ci_lines = ["jobs:", "  check:"]
        if codecov_enabled:
            ci_lines.extend(
                (
                    "  coverage:",
                    "    if: ${{ github.event_name == 'pull_request' }}",
                    "    permissions:",
                    "      contents: read",
                    "    steps:",
                    "      - name: Generate coverage report",
                    "        run: mise run coverage",
                    "        id: coverage",
                    "      - name: Resolve Codecov CLI",
                    "        id: codecov-cli",
                    "      - uses: codecov/codecov-action@v7",
                    "        binary: ${{ steps.codecov-cli.outputs.path }}",
                    "        files: ${{ steps.coverage.outputs.report }}",
                    "        disable_search: true",
                    "        fail_ci_if_error: true",
                    "      - name: Summary",
                    "        run: echo GITHUB_STEP_SUMMARY",
                )
            )
        if docs_enabled:
            ci_lines.extend(
                ("  docs:", "    name: Docs", "      run: mise run docs:build")
            )
            (template_root / "docs").mkdir()
            (template_root / "docs/package.json").write_text("{}\n", encoding="utf-8")
            (template_root / ".github/workflows/docs.yml").write_text(
                "name: Docs\n", encoding="utf-8"
            )
        if profile == "rust" and crates_io_enabled:
            ci_lines.extend(
                (
                    "      - name: Check crates.io package",
                    "        run: mise run crates-io:package:check",
                )
            )
        (template_root / ".github/workflows/ci.yml").write_text(
            "\n".join(ci_lines) + "\n", encoding="utf-8"
        )
        if codecov_enabled:
            (template_root / ".github/workflows/coverage.yml").write_text(
                "\n".join(
                    (
                        "on:",
                        "  push:",
                        "    branches: [main]",
                        "  workflow_dispatch:",
                        "concurrency:",
                        "  group: coverage-${{ github.ref }}",
                        "  cancel-in-progress: true",
                        "jobs:",
                        "  coverage:",
                        "    if: ${{ github.event_name == 'push' || github.ref == 'refs/heads/main' }}",
                        "    permissions:",
                        "      contents: read",
                        "      id-token: write",
                        "    steps:",
                        "      - name: Generate coverage report",
                        "        run: mise run coverage",
                        "        id: coverage",
                        "      - name: Resolve Codecov CLI",
                        "        id: codecov-cli",
                        "      - uses: codecov/codecov-action@v7",
                        "        binary: ${{ steps.codecov-cli.outputs.path }}",
                        "        files: ${{ steps.coverage.outputs.report }}",
                        "        disable_search: true",
                        "        fail_ci_if_error: true",
                        "        use_oidc: true",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
        release_lines = ["jobs:", "  release:"]
        if profile == "rust" and crates_io_enabled:
            release_lines.extend(
                (
                    "  publish-crate:",
                    "      - name: Publish crate",
                    "        run: mise run crates-io:publish",
                )
            )
            scripts_directory = template_root / "scripts"
            scripts_directory.mkdir()
            publish_script = scripts_directory / "publish-crate"
            publish_script.write_text("#!/bin/sh\n", encoding="utf-8")
            publish_script.chmod(0o755)
        if profile == "go-cli" and container_image_enabled:
            release_lines.extend(
                (
                    "  publish-container:",
                    "    needs: [version, release]",
                    "    permissions:",
                    "      packages: write",
                    "      - name: Authenticate with GHCR",
                    '        run: printf token | ko login ghcr.io --username actor --password-stdin',
                    "      - name: Publish container image",
                    "        env:",
                    "          CONTAINER_IMAGE_REPOSITORY: ghcr.io/YewFence/example-go-cli",
                    "          RELEASE_PRERELEASE: ${{ needs.version.outputs.prerelease }}",
                    "        run: mise run container:publish",
                )
            )
        (template_root / ".github/workflows/release.yml").write_text(
            "\n".join(release_lines) + "\n", encoding="utf-8"
        )
        tool_lines = ["[tools]", 'python = "3.14"']
        if docs_enabled:
            tool_lines.extend(('node = "26"', 'pnpm = "11"'))
        (template_root / "mise.toml").write_text(
            "\n".join(tool_lines) + "\n", encoding="utf-8"
        )
        if codecov_enabled:
            with (template_root / "mise.toml").open("a", encoding="utf-8") as handle:
                if profile == "common":
                    handle.write(
                        "\n[tasks.coverage]\n"
                        'description = "[PLACEHOLDER] Generate coverage.xml for Codecov upload"\n'
                        "run = 'echo \"[PLACEHOLDER] Replace coverage with a command that "
                        "generates coverage.xml in the repository root\" >&2; exit 1'\n"
                    )
                else:
                    handle.write(
                        "\n[tasks.coverage]\n"
                        "description = \"Generate coverage report\"\n"
                        "run = \"echo coverage\"\n"
                    )
        ci_tool_lines = ["[tools]", 'git-cliff = "latest"']
        if codecov_enabled:
            ci_tool_lines.append('"pipx:codecov-cli" = "11"')
            if profile == "rust":
                ci_tool_lines.append('"cargo:cargo-llvm-cov" = "0.8"')
        if profile == "rust" and crates_io_enabled:
            ci_tool_lines.append('jq = "1"')
        if profile == "go-cli" and container_image_enabled:
            ci_tool_lines.extend(
                (
                    '"aqua:ko-build/ko" = "0.19"',
                    '[tasks."container:build"]',
                    'run = "ko build --local --tags dev ./cmd/example-go-cli"',
                    '[tasks."container:publish"]',
                    'run = "ko build --bare --platform=all ./cmd/example-go-cli; tag_args+=(--tags latest); echo RELEASE_PRERELEASE must be true or false"',
                )
            )
        (template_root / "mise.ci.toml").write_text(
            "\n".join(ci_tool_lines) + "\n", encoding="utf-8"
        )
        if codecov_enabled:
            report = {"common": "coverage.xml", "go-cli": "coverage.out", "rust": "lcov.info"}[profile]
            (template_root / ".gitignore").write_text(f"/{report}\n", encoding="utf-8")
        (template_root / "tracked").write_text("tracked\n", encoding="utf-8")

    def initialize_repository(self, template_root: Path) -> None:
        subprocess.run(["git", "init", "--quiet"], cwd=template_root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=template_root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=template_root, check=True
        )
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"],
            cwd=template_root,
            check=True,
        )
        subprocess.run(["git", "add", "--all"], cwd=template_root, check=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "baseline"],
            cwd=template_root,
            check=True,
        )

    def write_mise_shim(
        self,
        path: Path,
        calls_path: Path,
        profile: str,
        enabled_capabilities: tuple[str, ...],
    ) -> dict[str, str]:
        tasks = ["actions:update", "check", "deps:update"]
        if "codecov-upload" in enabled_capabilities:
            tasks.append("coverage")
        if "docs-site" in enabled_capabilities:
            tasks.extend(
                (
                    "docs:build",
                    "docs:dev",
                    "docs:install",
                    "docs:install:locked",
                    "docs:lock",
                    "docs:preview",
                )
            )
        if profile == "rust" and "crates-io-publish" in enabled_capabilities:
            tasks.extend(("crates-io:package:check", "crates-io:publish"))
        if profile == "go-cli" and "container-image-publish" in enabled_capabilities:
            tasks.extend(("container:build", "container:publish"))
        path.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "if [ \"${1:-}\" = -C ]; then shift 2; fi\n"
            "if [ \"${1:-}\" = -E ]; then shift 2; fi\n"
            "case \"${1:-}\" in\n"
            "  lock) printf '%s\\n' 'lock' >> \"$MISE_CALLS_PATH\" ;;\n"
            "  install) printf '%s\\n' 'install --locked' >> \"$MISE_CALLS_PATH\" ;;\n"
            "  run)\n"
            "    shift\n"
            "    { printf 'run'; printf ' %s' \"$@\"; printf '\\n'; } >> \"$MISE_CALLS_PATH\"\n"
            "    ;;\n"
            "  tasks)\n"
            "    printf '%s\\n' \"$MISE_TASKS\"\n"
            "    ;;\n"
            "  *) echo \"unexpected mise command: $*\" >&2; exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return {
            "MISE_CALLS_PATH": str(calls_path),
            "MISE_TASKS": "\n".join(sorted(tasks)),
        }


if __name__ == "__main__":
    unittest.main()
