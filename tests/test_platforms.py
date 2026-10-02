"""Every platform module must import on the supported Home Assistant versions.

Platforms are only imported for devices that use them, so a removed Home
Assistant constant (like the vacuum STATE_* constants) can otherwise go
unnoticed until a user with that device upgrades.
"""

import importlib
from pathlib import Path

import pytest

# Import at collection time: the hass fixture later points the custom_components
# package at Home Assistant's testing config.
import custom_components.dyson_local  # noqa: F401

PLATFORM_MODULES = sorted(
    path.stem
    for path in (Path(__file__).parents[1] / "custom_components" / "dyson_local").glob("*.py")
    if path.stem != "__init__"
)


@pytest.mark.parametrize("module", PLATFORM_MODULES)
def test_platform_imports(module: str) -> None:
    importlib.import_module(f"custom_components.dyson_local.{module}")
