"""
mjolnir.tools.desktop
------------------------
Desktop integration tools: opening URLs in the default browser, launching
installed applications, and opening the default mail client. Uses
xdg-open / xdg-mime, the standard Freedesktop mechanisms on Debian-based
desktops (including Kali's XFCE), so it works with whatever the user has
configured as their default handlers.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger("mjolnir.tools.desktop")


def _xdg_open(target: str) -> dict[str, str | bool]:
    if shutil.which("xdg-open") is None:
        return {"ok": False, "output": "xdg-open not found. Install the 'xdg-utils' package."}
    try:
        subprocess.Popen(
            ["xdg-open", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"ok": True, "output": f"Opened: {target}"}
    except OSError as exc:
        return {"ok": False, "output": f"Failed to open {target}: {exc}"}


def open_url(url: str) -> dict[str, str | bool]:
    """Open a URL in the user's default web browser."""
    if not (url.startswith("http://") or url.startswith("https://")):
        url = f"https://{url}"
    return _xdg_open(url)


def open_application(name: str) -> dict[str, str | bool]:
    """Launch a desktop application by its executable/command name (e.g. 'firefox', 'thunar')."""
    if shutil.which(name) is None:
        return {"ok": False, "output": f"'{name}' was not found on PATH. Is it installed?"}
    try:
        subprocess.Popen(
            [name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"ok": True, "output": f"Launched: {name}"}
    except OSError as exc:
        return {"ok": False, "output": f"Failed to launch {name}: {exc}"}


def open_mail_client() -> dict[str, str | bool]:
    """Open the system's default mail client (mailto: handler)."""
    return _xdg_open("mailto:")


def open_file_manager(path: str = "~") -> dict[str, str | bool]:
    """Open the default file manager at the given path."""
    from pathlib import Path

    resolved = str(Path(path).expanduser())
    return _xdg_open(resolved)


from mjolnir.tools.registry import registry  # noqa: E402

registry.register(
    name="open_url",
    description="Open a URL in the user's default web browser.",
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string", "description": "The URL to open."}},
        "required": ["url"],
    },
)(open_url)

registry.register(
    name="open_application",
    description="Launch a desktop application on the local system by command name.",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Executable/command name, e.g. 'firefox'."}},
        "required": ["name"],
    },
)(open_application)

registry.register(
    name="open_mail_client",
    description="Open the system's default mail client.",
    parameters={"type": "object", "properties": {}},
)(open_mail_client)

registry.register(
    name="open_file_manager",
    description="Open the default file manager at a given directory path.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Directory to open (default: home)."}},
    },
)(open_file_manager)
