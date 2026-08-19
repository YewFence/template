from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
PUBLISH_SCRIPT = REPOSITORY_ROOT / "overlays/rust/static/scripts/publish-crate"


class TestPublishCrateScript:
    def test_existing_version_succeeds_without_token_or_publish(self) -> None:
        result, cargo_calls, user_agent = self.run_script(status="200")

        assert result.returncode == 0, result.stderr
        assert "Crate example-crate 1.2.3 already exists" in result.stdout
        assert user_agent == "example-crate-publish (https://github.com/{{GITHUB_OWNER}}/{{REPO_NAME}})"
        assert cargo_calls == ["metadata --locked --no-deps --format-version 1"]

    def test_missing_version_runs_dry_run_and_publish(self) -> None:
        result, cargo_calls, _ = self.run_script(status="404", token="trusted-token")

        assert result.returncode == 0, result.stderr
        assert "Crate example-crate 1.2.3 is not published yet" in result.stdout
        assert cargo_calls == [
            "metadata --locked --no-deps --format-version 1",
            "publish --dry-run --package example-crate --registry crates-io --locked",
            "publish --package example-crate --registry crates-io --locked",
        ]

    def test_missing_version_requires_token_after_dry_run(self) -> None:
        result, cargo_calls, _ = self.run_script(status="404")

        assert result.returncode != 0
        assert "crates.io trusted publishing did not provide a token" in result.stdout
        assert cargo_calls == [
            "metadata --locked --no-deps --format-version 1",
            "publish --dry-run --package example-crate --registry crates-io --locked",
        ]

    def test_package_version_must_match_release_version(self) -> None:
        result, cargo_calls, _ = self.run_script(
            status="404",
            crate_version="1.2.4",
        )

        assert result.returncode != 0
        assert "Cargo package version 1.2.4 does not match release tag v1.2.3" in result.stdout
        assert cargo_calls == ["metadata --locked --no-deps --format-version 1"]

    def run_script(
        self,
        *,
        status: str,
        crate_version: str = "1.2.3",
        token: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], list[str], str | None]:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            binary_directory = temporary_root / "bin"
            binary_directory.mkdir()
            cargo_calls_path = temporary_root / "cargo-calls"
            curl_user_agent_path = temporary_root / "curl-user-agent"
            self.write_shims(binary_directory)

            environment = os.environ | {
                "PATH": f"{binary_directory}:{os.environ['PATH']}",
                "FAKE_CARGO_CALLS": str(cargo_calls_path),
                "FAKE_CURL_USER_AGENT": str(curl_user_agent_path),
                "FAKE_CRATE_NAME": "example-crate",
                "FAKE_CRATE_VERSION": crate_version,
                "FAKE_CRATES_IO_STATUS": status,
                "FAKE_PACKAGE_COUNT": "1",
                "RELEASE_TAG": "v1.2.3",
                "RELEASE_VERSION": "1.2.3",
            }
            if token is not None:
                environment["CARGO_REGISTRY_TOKEN"] = token
            else:
                environment.pop("CARGO_REGISTRY_TOKEN", None)

            result = subprocess.run(
                [str(PUBLISH_SCRIPT)],
                cwd=temporary_root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            cargo_calls = (
                cargo_calls_path.read_text(encoding="utf-8").splitlines()
                if cargo_calls_path.exists()
                else []
            )
            user_agent = (
                curl_user_agent_path.read_text(encoding="utf-8")
                if curl_user_agent_path.exists()
                else None
            )
            return result, cargo_calls, user_agent

    def write_shims(self, binary_directory: Path) -> None:
        cargo = binary_directory / "cargo"
        cargo.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf '%s\\n' \"$*\" >> \"${FAKE_CARGO_CALLS}\"\n"
            "if [[ \"${1:-}\" == metadata ]]; then\n"
            "  printf '%s\\n' '{\"packages\":[]}'\n"
            "fi\n",
            encoding="utf-8",
        )
        cargo.chmod(0o755)

        jq = binary_directory / "jq"
        jq.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "case \"$*\" in\n"
            "  *'.packages | length'*) printf '%s\\n' \"${FAKE_PACKAGE_COUNT}\" ;;\n"
            "  *'.packages[0].name'*) printf '%s\\n' \"${FAKE_CRATE_NAME}\" ;;\n"
            "  *'.packages[0].version'*) printf '%s\\n' \"${FAKE_CRATE_VERSION}\" ;;\n"
            "  *) echo \"unexpected jq query: $*\" >&2; exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        jq.chmod(0o755)

        curl = binary_directory / "curl"
        curl.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "output=''\n"
            "user_agent=''\n"
            "while [[ $# -gt 0 ]]; do\n"
            "  case \"$1\" in\n"
            "    --output) output=\"$2\"; shift 2 ;;\n"
            "    --user-agent) user_agent=\"$2\"; shift 2 ;;\n"
            "    *) shift ;;\n"
            "  esac\n"
            "done\n"
            "printf '%s' \"${user_agent}\" > \"${FAKE_CURL_USER_AGENT}\"\n"
            "printf '%s\\n' '{}' > \"${output}\"\n"
            "printf '%s' \"${FAKE_CRATES_IO_STATUS}\"\n",
            encoding="utf-8",
        )
        curl.chmod(0o755)
