"""Shared fixtures for validation adapter tests.

Stages a disposable unbootstrapped template tree per profile and capability
set, records adapter `mise` invocations through a PATH shim, and offers two
invocation layers: the primary direct adapter entry and a thin namespaced
mise task path. Docs-site, Codecov, and profile-specific staging logic lives
here exactly once; test modules parametrize over profiles instead of
duplicating fixtures.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[3]

PROFILE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "common": ("codecov-upload", "docs-site"),
    "python": ("codecov-upload", "docs-site"),
    "go-cli": ("codecov-upload", "container-image-publish", "docs-site"),
    "rust": ("codecov-upload", "crates-io-publish", "docs-site"),
}


def capability_environment(capabilities: tuple[str, ...]) -> str:
    """Serialize the adapter capability environment exactly as template-tool does."""
    return json.dumps(capabilities, separators=(",", ":"))


class AdapterFailure(AssertionError):
    """A validation adapter exited non-zero.

    The message names the profile, the capability case, and the adapter's
    stderr so a failing test points at the contract that broke instead of a
    bare Bash exit code.
    """

    def __init__(self, profile: str, enabled_capabilities: tuple[str, ...], stderr: str) -> None:
        self.profile = profile
        self.enabled_capabilities = enabled_capabilities
        self.stderr = stderr
        case = ", ".join(enabled_capabilities) or "no capabilities"
        super().__init__(f"adapter {profile} failed for capability case [{case}]:\n{stderr.strip()}")


class StagingHarness:
    """Stage projects, shim mise, and invoke validation adapters."""

    @contextmanager
    def staged_repository(
        self,
        profile: str,
        enabled_capabilities: tuple[str, ...],
    ) -> Iterator[Path]:
        """Yield a temporary repository root with a staged template tree.

        The root contains `template/` (the staged project committed as a Git
        baseline), `bin/mise` (the recording shim), and `mise-calls` (the
        recorded invocation log).
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_root = root / "template"
            template_root.mkdir()
            self.write_staged_project(template_root, profile, enabled_capabilities)
            self.initialize_repository(template_root)
            yield root

    def environment_for(
        self,
        root: Path,
        profile: str,
        enabled_capabilities: tuple[str, ...],
        staged_capabilities: tuple[str, ...],
    ) -> dict[str, str]:
        """Build the adapter environment: shim first on PATH plus capability env."""
        binary_directory = root / "bin"
        binary_directory.mkdir(exist_ok=True)
        calls_path = root / "mise-calls"
        shim_environment = self.write_mise_shim(
            binary_directory / "mise",
            calls_path,
            profile,
            staged_capabilities,
        )
        return os.environ | {
            "PATH": f"{binary_directory}:{os.environ['PATH']}",
            "TEMPLATE_TOOL_ENABLED_CAPABILITIES": capability_environment(enabled_capabilities),
            "TEMPLATE_TOOL_VALIDATION_BIN": str(binary_directory),
        } | shim_environment

    def invoke_adapter(
        self,
        root: Path,
        profile: str,
        enabled_capabilities: tuple[str, ...],
        staged_capabilities: tuple[str, ...],
        *,
        task_name: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one adapter against an existing staged repository.

        Without `task_name` the primary Python adapter entry is invoked
        directly. With a namespaced task name like `//overlays/common:check`,
        real mise resolves the adapter registration from the repository root
        while the adapter's own mise calls still resolve to the PATH shim.
        """
        template_root = root / "template"
        if environment is None:
            environment = self.environment_for(root, profile, enabled_capabilities, staged_capabilities)
        if task_name is None:
            command = [
                sys.executable,
                str(REPOSITORY_ROOT / "overlays" / profile / "validation/check.py"),
                str(template_root),
            ]
        else:
            real_mise = shutil.which("mise")
            assert real_mise is not None, "real mise binary must be on PATH"
            command = [real_mise, "run", task_name, str(template_root)]
        return subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=environment,
            text=True,
            capture_output=True,
        )

    def run_adapter(
        self,
        profile: str,
        enabled_capabilities: tuple[str, ...],
        *,
        staged_capabilities: tuple[str, ...] | None = None,
    ) -> list[str]:
        """Run an adapter against a fresh staged project and return recorded mise calls.

        Raises AdapterFailure naming the profile, capability case, and adapter
        stderr when the adapter exits non-zero.
        """
        if staged_capabilities is None:
            staged_capabilities = enabled_capabilities
        with self.staged_repository(profile, staged_capabilities) as root:
            completed = self.invoke_adapter(root, profile, enabled_capabilities, staged_capabilities)
            if completed.returncode != 0:
                raise AdapterFailure(profile, enabled_capabilities, completed.stderr)
            return (root / "mise-calls").read_text(encoding="utf-8").splitlines()

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
            coverage_run = (
                ("        run: |", "          mise run coverage")
                if profile == "rust"
                else ("        run: mise run coverage",)
            )
            ci_lines.extend(
                (
                    "  coverage:",
                    "    if: ${{ github.event_name == 'pull_request' }}",
                    "    permissions:",
                    "      contents: read",
                    "    steps:",
                    "      - name: Generate coverage report",
                    *coverage_run,
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
        if profile == "python":
            tool_lines.extend(('uv = "0"', 'ruff = "0.16"', 'ty = "0.0"'))
        if docs_enabled:
            tool_lines.extend(('node = "26"', 'pnpm = "11"'))
        (template_root / "mise.toml").write_text(
            "\n".join(tool_lines) + "\n", encoding="utf-8"
        )
        if profile == "python":
            package = template_root / "src/example_python_project"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text('"""Example package."""\n', encoding="utf-8")
            tests = template_root / "tests"
            tests.mkdir()
            (tests / "test_package.py").write_text(
                "def test_package():\n    assert True\n", encoding="utf-8"
            )
            coverage_group = (
                '\ncoverage = ["pytest-cov>=7,<8"]' if codecov_enabled else ""
            )
            (template_root / "pyproject.toml").write_text(
                "[project]\n"
                'name = "example-python-project"\n'
                'version = "0.1.0"\n'
                'requires-python = ">=3.12"\n'
                "dependencies = []\n\n"
                "[dependency-groups]\n"
                'dev = ["pytest>=9,<10"]'
                f"{coverage_group}\n\n"
                "[build-system]\n"
                'requires = ["hatchling>=1,<2"]\n'
                'build-backend = "hatchling.build"\n\n'
                "[tool.hatch.build.targets.wheel]\n"
                'packages = ["src/example_python_project"]\n',
                encoding="utf-8",
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
            report = {
                "common": "coverage.xml",
                "python": "coverage.xml",
                "go-cli": "coverage.out",
                "rust": "lcov.info",
            }[profile]
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
        if profile == "python":
            tasks.extend(
                (
                    "audit",
                    "build",
                    "build:check",
                    "deps:check",
                    "deps:fix",
                    "fmt:check",
                    "fmt:fix",
                    "lint",
                    "lint:fix",
                    "test",
                )
            )
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
