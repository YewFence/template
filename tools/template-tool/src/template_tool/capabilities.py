from __future__ import annotations

import re
from collections.abc import Iterable, Mapping


CAPABILITY_NAME_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


class CapabilityError(ValueError):
    """Raised when a capability contract or selection is invalid."""


def validate_capabilities(raw: object, profile: str) -> dict[str, bool]:
    if not isinstance(raw, dict):
        raise CapabilityError(f"templates.{profile}.capabilities must be a table")

    capabilities: dict[str, bool] = {}
    for name, default_enabled in raw.items():
        if not isinstance(name, str) or not CAPABILITY_NAME_PATTERN.fullmatch(name):
            raise CapabilityError(
                f"templates.{profile}.capabilities contains invalid capability name: {name!r}"
            )
        if type(default_enabled) is not bool:
            raise CapabilityError(
                f"templates.{profile}.capabilities.{name} must be a boolean"
            )
        capabilities[name] = default_enabled
    return capabilities


def resolve_capabilities(
    capabilities: Mapping[str, bool],
    *,
    enable: Iterable[str] = (),
    disable: Iterable[str] = (),
) -> tuple[str, ...]:
    enabled_overrides = set(enable)
    disabled_overrides = set(disable)
    invalid = {
        name
        for name in enabled_overrides | disabled_overrides
        if not isinstance(name, str) or not CAPABILITY_NAME_PATTERN.fullmatch(name)
    }
    if invalid:
        names = ", ".join(sorted(repr(name) for name in invalid))
        raise CapabilityError(f"invalid capability names: {names}")

    conflicts = enabled_overrides & disabled_overrides
    if conflicts:
        names = ", ".join(sorted(conflicts))
        raise CapabilityError(f"capabilities both enabled and disabled: {names}")

    undeclared = (enabled_overrides | disabled_overrides) - set(capabilities)
    if undeclared:
        names = ", ".join(sorted(undeclared))
        raise CapabilityError(f"capabilities not applicable to this template: {names}")

    effective = {
        name for name, default_enabled in capabilities.items() if default_enabled
    }
    effective.update(enabled_overrides)
    effective.difference_update(disabled_overrides)
    return tuple(sorted(effective))
