"""Hermes Chrome extension bridge for browser control."""

from __future__ import annotations

from pathlib import Path

from .tools import (
    HERMES_CHROME_BROWSER_SCHEMA,
    _check_hermes_chrome_available,
    _handle_hermes_chrome_browser,
)


def register(ctx) -> None:
    """Register the Hermes Chrome bridge tool and explicit skill."""
    ctx.register_tool(
        name="hermes_chrome_browser",
        toolset="hermes_chrome",
        schema=HERMES_CHROME_BROWSER_SCHEMA,
        handler=_handle_hermes_chrome_browser,
        check_fn=_check_hermes_chrome_available,
        emoji="🌐",
    )
    ctx.register_skill(
        "hermes-chrome",
        Path(__file__).resolve().parent / "skills" / "hermes-chrome" / "SKILL.md",
        "Control Chrome through the Hermes extension bridge.",
    )
