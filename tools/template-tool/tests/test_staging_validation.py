from __future__ import annotations

import pytest

from template_tool.staging_validation import ValidationError, parse_enabled_capabilities


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
