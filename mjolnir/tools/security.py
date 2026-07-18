"""
mjolnir.tools.security
-------------------------
Thin wrappers around standard Kali/Debian security tools (nmap, nikto,
wpscan). These exist so Mjolnir can help with recon and vulnerability
scanning against systems the user is authorized to test.

Unlike the general terminal tool, EVERY invocation here requires an
explicit, per-call user confirmation naming the exact target — even if
the general "confirm destructive commands" setting is turned off. The
agent cannot chain these into an automatic exploitation sequence; they
only run, report output, and stop. There is no auto-exploit, auto-report,
or Metasploit bridging here by design.

Only run these against systems and networks you own or have explicit
written authorization to test. Scanning systems without authorization
is illegal in most jurisdictions.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable

logger = logging.getLogger("mjolnir.tools.security")

ConfirmHook = Callable[[str], bool]
_confirm_hook: ConfirmHook | None = None

DEFAULT_TIMEOUT = 300


def set_confirm_hook(hook: ConfirmHook) -> None:
    global _confirm_hook
    _confirm_hook = hook


def _require_confirmation(tool: str, target: str, extra: str = "") -> bool:
    description = (
        f"Run {tool} against '{target}'{extra}. Only proceed if you are authorized "
        f"to test this target."
    )
    if _confirm_hook is None:
        # No UI wired up (e.g. non-interactive mode) — refuse rather than run silently.
        logger.warning("Security tool %s blocked: no confirmation hook available.", tool)
        return False
    return _confirm_hook(description)


def _run(cmd: list[str], timeout: int) -> dict[str, str | bool]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return {"ok": result.returncode == 0, "output": output.strip() or "(no output)"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"{cmd[0]} timed out after {timeout}s."}
    except OSError as exc:
        return {"ok": False, "output": f"Execution failed: {exc}"}


def run_nmap_scan(target: str, options: str = "-sV -T4", timeout: int = DEFAULT_TIMEOUT) -> dict[str, str | bool]:
    """Run an nmap scan against a target. Requires explicit per-call confirmation."""
    if shutil.which("nmap") is None:
        return {"ok": False, "output": "nmap is not installed."}
    if not _require_confirmation("nmap", target, f" with options '{options}'"):
        return {"ok": False, "output": "Scan not executed: user did not confirm this target."}
    cmd = ["nmap", *options.split(), target]
    return _run(cmd, timeout)


def run_nikto_scan(target: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, str | bool]:
    """Run a nikto web server scan against a target URL/host. Requires per-call confirmation."""
    if shutil.which("nikto") is None:
        return {"ok": False, "output": "nikto is not installed."}
    if not _require_confirmation("nikto", target):
        return {"ok": False, "output": "Scan not executed: user did not confirm this target."}
    cmd = ["nikto", "-h", target]
    return _run(cmd, timeout)


def run_wpscan(target: str, options: str = "--enumerate vp", timeout: int = DEFAULT_TIMEOUT) -> dict[str, str | bool]:
    """Run a wpscan WordPress scan against a target URL. Requires per-call confirmation."""
    if shutil.which("wpscan") is None:
        return {"ok": False, "output": "wpscan is not installed."}
    if not _require_confirmation("wpscan", target, f" with options '{options}'"):
        return {"ok": False, "output": "Scan not executed: user did not confirm this target."}
    cmd = ["wpscan", "--url", target, *options.split()]
    return _run(cmd, timeout)


from mjolnir.tools.registry import registry  # noqa: E402

registry.register(
    name="run_nmap_scan",
    description=(
        "Run an nmap network scan against a target host/IP the user is authorized to test. "
        "Always requires explicit user confirmation of the target before running."
    ),
    parameters={
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Target host or IP address."},
            "options": {"type": "string", "description": "nmap flags, e.g. '-sV -T4' (default)."},
            "timeout": {"type": "integer", "description": "Timeout in seconds."},
        },
        "required": ["target"],
    },
)(run_nmap_scan)

registry.register(
    name="run_nikto_scan",
    description=(
        "Run a nikto web server vulnerability scan against a target the user is authorized "
        "to test. Always requires explicit user confirmation of the target before running."
    ),
    parameters={
        "type": "object",
        "properties": {"target": {"type": "string", "description": "Target URL or host."}},
        "required": ["target"],
    },
)(run_nikto_scan)

registry.register(
    name="run_wpscan",
    description=(
        "Run a wpscan WordPress scan against a target the user is authorized to test. "
        "Always requires explicit user confirmation of the target before running."
    ),
    parameters={
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Target WordPress site URL."},
            "options": {"type": "string", "description": "wpscan flags, e.g. '--enumerate vp' (default)."},
        },
        "required": ["target"],
    },
)(run_wpscan)
