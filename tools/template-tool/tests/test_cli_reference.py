from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from template_tool import cli
from template_tool import cli_reference


class RenderReferenceTest(unittest.TestCase):
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
            self.assertIn(f"`{prog}`", content)
        for subcommand in ("render", "check", "apply", "init", "export", "capabilities"):
            self.assertIn(f"`template-tool {subcommand}`", content)

    def test_embeds_verbatim_help_output(self) -> None:
        content = cli_reference.render_reference()
        for parser in (*cli.user_parsers(), *cli.maintenance_parsers(), cli.umbrella_parser()):
            self.assertIn(parser.format_help().rstrip(), content)

    def test_output_is_deterministic(self) -> None:
        self.assertEqual(cli_reference.render_reference(), cli_reference.render_reference())


class CheckModeTest(unittest.TestCase):
    def test_check_passes_when_in_sync_and_fails_on_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "cli.md"
            with self.assertRaises(SystemExit) as missing:
                cli_reference.main(["--check", str(output)])
            self.assertEqual(missing.exception.code, 1)
            cli_reference.main([str(output)])
            self.assertTrue(output.is_file())
            cli_reference.main(["--check", str(output)])
            output.write_text("stale\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as drifted:
                cli_reference.main(["--check", str(output)])
            self.assertEqual(drifted.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
