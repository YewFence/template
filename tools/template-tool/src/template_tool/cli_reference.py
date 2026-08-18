"""Generate the CLI reference markdown from the live argparse parsers.

The generated document embeds each entry point's verbatim ``--help`` output,
so the reference can never drift from the CLI itself. Run it through the
monorepo mise tasks ``docs:reference`` (write) and ``docs:reference:check``
(read-only drift check).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import cli

_DEFAULT_OUTPUT = Path("docs/reference/cli.md")

_INTRO = """\
# CLI Reference

<!-- GENERATED FILE: do not edit by hand. Regenerate with `mise run docs:reference`. -->

This reference is generated from the tool's own `--help` output. Run any entry point with `--help` to see the same text interactively.

The user-facing commands are usually run through `uvx`, which fetches the selected ref of the template monorepo and executes its locked tool version:

```text
uvx --from "git+https://github.com/YewFence/template.git@main#subdirectory=tools/template-tool" <command> ...
```
"""


def _section(parser: argparse.ArgumentParser, level: int) -> str:
    return f"{'#' * level} `{parser.prog}`\n\n```text\n{parser.format_help().rstrip()}\n```\n"


def render_reference() -> str:
    """Build the full CLI reference markdown from the live parsers."""
    # argparse wraps help text at the terminal width; pin it so the generated
    # file is identical on every machine and in CI.
    os.environ["COLUMNS"] = "80"
    sections = [_INTRO, "## User Commands"]
    sections.extend(_section(parser, 3) for parser in cli.user_parsers())
    sections.append("## Maintenance Commands")
    sections.extend(_section(parser, 3) for parser in cli.maintenance_parsers())
    umbrella = cli.umbrella_parser()
    sections.append(_section(umbrella, 3))
    subparsers = next(
        action
        for action in umbrella._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    sections.extend(_section(subcommand, 4) for subcommand in subparsers.choices.values())
    return "\n\n".join(section.rstrip("\n") for section in sections) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="generate-cli-reference",
        description="Generate the CLI reference markdown from the live --help output.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="markdown file to write (default: %(default)s)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the committed file with the generated content without writing",
    )
    args = parser.parse_args(argv)
    content = render_reference()
    if args.check:
        try:
            committed = args.output.read_text(encoding="utf-8")
        except OSError:
            committed = None
        if committed != content:
            print(f"{args.output}: generated output differs", file=sys.stderr)
            raise SystemExit(1)
        print(f"{args.output}: in sync")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"{args.output}: written")


if __name__ == "__main__":
    main()
