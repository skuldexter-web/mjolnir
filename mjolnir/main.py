"""
mjolnir.main
-------------
CLI entrypoint. Installed as the global `mjolnir` command.
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
from pathlib import Path

from mjolnir import __version__
from mjolnir.config.settings import LOG_DIR, Settings


def _setup_logging(settings: Settings) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, str(settings.logging.get("level", "INFO")).upper(), logging.INFO)
    max_bytes = int(settings.logging.get("max_bytes", 2_000_000))
    backup_count = int(settings.logging.get("backup_count", 5))

    root = logging.getLogger("mjolnir")
    root.setLevel(level)
    root.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    for stream_name in settings.logging.get("streams", ["session"]):
        handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / f"{stream_name}.log", maxBytes=max_bytes, backupCount=backup_count
        )
        handler.setFormatter(fmt)
        root.addHandler(handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mjolnir",
        description="MJOLNIR — local, Ollama-only terminal AI agent for Debian-based Linux.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"mjolnir {__version__}")
    parser.add_argument("--model", help="Override the model for this session (Qwen/Gemma, <=14B).")
    parser.add_argument("--anon", action="store_true", help="Enable anonymous mode (route via Tor) for this session.")
    parser.add_argument(
        "-i", "--instruction", help="Run a single instruction non-interactively and exit."
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    settings = Settings.load()
    if args.model:
        from mjolnir.config.settings import validate_model

        try:
            validate_model(args.model)
        except ValueError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 1
        settings.model = args.model
    if args.anon:
        settings.anonymous_mode = True

    _setup_logging(settings)

    from mjolnir.interface.tui import MjolnirTUI

    app = MjolnirTUI()
    app.settings = settings

    if args.instruction:
        if not app._preflight():
            return 1
        app.loop.run_turn(args.instruction)
        return 0

    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
