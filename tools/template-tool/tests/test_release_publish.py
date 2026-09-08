from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "shared/static/.github/scripts/publish-release.sh"


@pytest.fixture
def publisher(tmp_path: Path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
         "commit", "--quiet", "--allow-empty", "-m", "Initial"],
        cwd=tmp_path, check=True,
    )
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True,
    ).strip()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_bytes((Path(__file__).parent / "fixtures/gh_release.py").read_bytes())
    gh.chmod(0o755)
    notes = tmp_path / "release notes.md"
    notes.write_text("Release notes\n")
    assets = tmp_path / "dist"
    assets.mkdir()
    (assets / "project linux.tar.gz").write_text("archive")
    (assets / "SHA256SUMS").write_text("checksums")
    state_path = tmp_path / "gh-state.json"

    def run(*, release="missing", tag_exists=False, allow=True, with_assets=True,
            extra_env=None, **state_overrides):
        state_path.write_text(json.dumps({
            "release": release, "tag_exists": tag_exists, "tag_commit": commit,
            **state_overrides,
        }))
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "GH_TEST_STATE": str(state_path),
            "GH_REPO": "example/project",
            "RELEASE_TAG": "v1.2.3",
            "RELEASE_COMMIT": commit,
            "ALLOW_TAG_CREATION": str(allow).lower(),
            "RELEASE_PRERELEASE": "false",
            "RELEASE_NOTES_FILE": str(notes),
            "RELEASE_ASSET_DIR": str(assets) if with_assets else "",
            **(extra_env or {}),
        }
        result = subprocess.run(
            ["bash", str(SCRIPT)], cwd=tmp_path, env=env, text=True,
            capture_output=True,
        )
        return result, json.loads(state_path.read_text())

    return run, tmp_path, commit


@pytest.mark.parametrize("with_assets", [False, True])
@pytest.mark.parametrize("allow", [False, True])
def test_create_uses_cli_asset_publication_and_exact_target(publisher, with_assets, allow):
    run, root, commit = publisher
    result, state = run(allow=allow, tag_exists=not allow, with_assets=with_assets)
    assert result.returncode == 0, result.stderr
    writes = [call for call in state["calls"] if call[0] == "release"]
    assert len(writes) == 1
    command = writes[0]
    assert command[:3] == ["release", "create", "v1.2.3"]
    assert command[command.index("--target") + 1] == commit
    assert command[command.index("--notes-file") + 1] == str(root / "release notes.md")
    assert ("--verify-tag" in command) is (not allow)
    assert "--latest" not in command
    assert "--draft" not in command
    assert (str(root / "dist/project linux.tar.gz") in command) is with_assets
    assert (str(root / "dist/SHA256SUMS") in command) is with_assets
    if not allow:
        assert ["api", "repos/example/project/commits/refs%2Ftags%2Fv1.2.3", "--jq", ".sha"] in state["calls"]


@pytest.mark.parametrize("release", ["draft", "published"])
@pytest.mark.parametrize("with_assets", [False, True])
def test_rerun_uploads_before_edit_without_resetting_title_or_extra_assets(
    publisher, release, with_assets,
):
    run, _, _ = publisher
    result, state = run(release=release, tag_exists=True, with_assets=with_assets)
    assert result.returncode == 0, result.stderr
    writes = [call for call in state["calls"] if call[0] == "release"]
    assert [call[1] for call in writes] == (["upload", "edit"] if with_assets else ["edit"])
    if with_assets:
        assert "--clobber" in writes[0]
    assert ("--draft=false" in writes[-1]) is (release == "draft")
    assert "--prerelease=false" in writes[-1]
    for call in writes:
        assert "--title" not in call
        assert "--latest" not in call
        assert "delete" not in call


def test_draft_without_tag_can_resume_only_on_auto_tag_path(publisher):
    run, _, commit = publisher
    result, state = run(release="draft")
    assert result.returncode == 0, result.stderr
    edit = state["calls"][-1]
    assert edit[:2] == ["release", "edit"]
    assert edit[edit.index("--target") + 1] == commit
    assert "--draft=false" in edit
    result, state = run(release="draft", allow=False)
    assert result.returncode != 0
    assert not any(call[0] == "release" for call in state["calls"])


@pytest.mark.parametrize("release", ["missing", "draft", "published"])
def test_conflicting_remote_tag_fails_before_writes(publisher, release):
    run, _, _ = publisher
    result, state = run(release=release, tag_exists=True, tag_commit="0" * 40)
    assert result.returncode != 0
    assert "does not match" in result.stderr
    assert not any(call[0] == "release" for call in state["calls"])


@pytest.mark.parametrize("error", ["query_error", "commit_error", "repository_missing"])
def test_lookup_failure_is_not_treated_as_missing_release(publisher, error):
    run, _, _ = publisher
    result, state = run(tag_exists=True, **{error: True})
    assert result.returncode != 0
    assert not any(call[0] == "release" for call in state["calls"])


@pytest.mark.parametrize("release", ["draft", "published"])
def test_upload_failure_does_not_publish_or_edit(publisher, release):
    run, _, _ = publisher
    result, state = run(release=release, tag_exists=True, upload_error=True)
    assert result.returncode != 0
    assert state["release"] == release
    assert state["calls"][-1][:2] == ["release", "upload"]


@pytest.mark.parametrize("release,error", [("missing", "create_error"), ("published", "edit_error")])
def test_mutation_errors_are_propagated_without_rollback(publisher, release, error):
    run, _, _ = publisher
    result, state = run(release=release, tag_exists=True, **{error: True})
    assert result.returncode != 0
    assert not any("delete" in call for call in state["calls"])


def test_required_assets_must_exist_before_remote_calls(publisher):
    run, root, _ = publisher
    for asset in (root / "dist").iterdir():
        asset.unlink()
    result, state = run()
    assert result.returncode != 0
    assert "No release assets" in result.stderr
    assert not state.get("calls")


@pytest.mark.parametrize("release", ["missing", "published"])
def test_prerelease_flag_is_explicit(publisher, release):
    run, _, _ = publisher
    result, state = run(release=release, tag_exists=True, extra_env={
        "RELEASE_TAG": "v1.2.3-rc.1", "RELEASE_PRERELEASE": "true",
    })
    assert result.returncode == 0, result.stderr
    assert "--prerelease=true" in state["calls"][-1]


def test_checkout_must_match_resolved_commit(publisher):
    run, _, _ = publisher
    result, state = run(extra_env={"RELEASE_COMMIT": "0" * 40})
    assert result.returncode != 0
    assert not state.get("calls")


def test_missing_tag_is_rejected_on_existing_tag_entrypoint(publisher):
    run, _, _ = publisher
    result, state = run(allow=False)
    assert result.returncode != 0
    assert "must already exist" in result.stderr
    assert not any(call[0] == "release" for call in state["calls"])


@pytest.mark.parametrize("field,value", [
    ("ALLOW_TAG_CREATION", "yes"),
    ("RELEASE_PRERELEASE", "yes"),
    ("RELEASE_TAG", "--help"),
    ("RELEASE_COMMIT", "main"),
    ("RELEASE_NOTES_FILE", "/missing/notes"),
])
def test_invalid_inputs_fail_before_remote_calls(publisher, field, value):
    run, _, _ = publisher
    result, state = run(extra_env={field: value})
    assert result.returncode != 0
    assert not state.get("calls")
