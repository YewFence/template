from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from template_tool import cli
from template_tool import cli_reference


class TestRenderReference:
    def test_contains_every_entry_point(self) -> None:
        content = cli_reference.render_reference()
        for prog in (
            "init-project",
            "apply-template",
            "export-template",
            "list-template-capabilities",
            "render-template",
            "check-templates",
            "template-tool",
        ):
            assert f"`{prog}`" in content
        for subcommand in ("render", "check", "apply", "init", "export", "capabilities"):
            assert f"`template-tool {subcommand}`" in content

    def test_embeds_verbatim_help_output(self) -> None:
        content = cli_reference.render_reference()
        for parser in (*cli.user_parsers(), *cli.maintenance_parsers(), cli.umbrella_parser()):
            assert parser.format_help().rstrip() in content

    def test_output_is_deterministic(self) -> None:
        assert cli_reference.render_reference() == cli_reference.render_reference()


class TestCheckMode:
    def test_check_passes_when_in_sync_and_fails_on_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "cli.md"
            with pytest.raises(SystemExit) as missing:
                cli_reference.main(["--check", str(output)])
            assert missing.value.code == 1
            cli_reference.main([str(output)])
            assert output.is_file()
            cli_reference.main(["--check", str(output)])
            output.write_text("stale\n", encoding="utf-8")
            with pytest.raises(SystemExit) as drifted:
                cli_reference.main(["--check", str(output)])
            assert drifted.value.code == 1
