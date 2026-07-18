"""
mjolnir.tools.terminal
------------------------
Shell execution tool. This is the highest-risk capability in Mjolnir,
so every command passes through a denylist of destructive patterns and,
depending on config, an interactive confirmation prompt before running.

This module intentionally does NOT attempt to be a sandbox. It runs
commands with the same privileges as the user who started Mjolnir. The
guardrails here catch obviously destructive patterns; they are not a
security boundary against a malicious or compromised model.
"""

from __future__ import annotations

import logging
import re
import shlex
import subprocess
from collections.abc import Callable

from mjolnir.config.settings import Settings

logger = logging.getLogger("mjolnir.tools.terminal")

# Optional hook the TUI can set to prompt the user for y/n confirmation.
# Signature: (command: str) -> bool
ConfirmHook = Callable[[str], bool]

_confirm_hook: ConfirmHook | None = None


def set_confirm_hook(hook: ConfirmHook) -> None:
    global _confirm_hook
    _confirm_hook = hook


def _is_denied(command: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        if re.search(pattern, command):
            return pattern
    return None


def _looks_destructive(command: str) -> bool:
    destructive_tokens = (
        "rm ", "rm\t", "mkfs", "dd ", "shred", "chmod -R", "chown -R",
        "> /dev/", "userdel", "deluser", "iptables -F", "ufw --force",
        "systemctl stop", "systemctl disable", "kill -9",
    )
    return any(tok in command for tok in destructive_tokens)


def run_command(command: str, cwd: str | None = None, timeout: int | None = None) -> dict[str, str | bool]:
    """
    Execute a shell command on the local Debian system.

    Args:
        command: the shell command to run.
        cwd: optional working directory.
        timeout: optional override for the max execution time in seconds.
    """
    settings = Settings.load()
    denied_reason = _is_denied(command, settings.safety.denied_command_patterns)
    if denied_reason:
        logger.warning("Blocked command matching denylist pattern %r: %s", denied_reason, command)
        return {
            "ok": False,
            "output": f"Refused: command matches a blocked destructive pattern ({denied_reason}).",
        }

    if settings.safety.confirm_destructive_commands and _looks_destructive(command):
        if _confirm_hook is None or not _confirm_hook(command):
            return {"ok": False, "output": "Command not executed: user did not confirm a destructive action."}

    try:
        parsed = shlex.split(command)
    except ValueError as exc:
        return {"ok": False, "output": f"Could not parse command: {exc}"}

    if not parsed:
        return {"ok": False, "output": "Empty command."}

    effective_timeout = timeout or settings.safety.max_command_timeout_seconds

    try:
        result = subprocess.run(
            command,
            shell=True,  # nosec B602 - deliberate, gated by denylist + confirmation above
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return {"ok": result.returncode == 0, "output": output.strip() or "(no output)"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"Command timed out after {effective_timeout}s."}
    except OSError as exc:
        return {"ok": False, "output": f"Execution failed: {exc}"}


from mjolnir.tools.registry import registry  # noqa: E402

registry.register(
    name="run_command",
    description=(
        "Execute a shell command on the local Debian-based system and return its "
        "combined stdout/stderr. Destructive commands may require user confirmation "
        "or be refused outright."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute."},
            "cwd": {"type": "string", "description": "Optional working directory."},
            "timeout": {"type": "integer", "description": "Optional timeout override in seconds."},
        },
        "required": ["command"],
    },
)(run_command)
