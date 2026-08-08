from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
TOP_LEVEL_KEYS = frozenset({"version", "apply", "templates"})


class ConfigurationError(ValueError):
    """Raised when templates.toml violates the shared schema contract."""


def load_template_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as config_file:
            config = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(f"cannot load templates.toml: {error}") from error

    if config.get("version") != SCHEMA_VERSION:
        raise ConfigurationError(
            f"templates.toml must declare version = {SCHEMA_VERSION}"
        )
    unknown = set(config) - TOP_LEVEL_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigurationError(f"unknown top-level keys: {names}")
    return config
