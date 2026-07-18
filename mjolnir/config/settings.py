"""
mjolnir.config.settings
------------------------
Loads and validates Mjolnir's configuration.

Config lives at ~/.config/mjolnir/config.yaml and is created on first run
with safe defaults. Only Ollama is supported as an inference backend, and
only Qwen / Gemma family models under 14B parameters are permitted.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(os.environ.get("MJOLNIR_HOME", Path.home() / ".config" / "mjolnir"))
CONFIG_FILE = CONFIG_DIR / "config.yaml"
LOG_DIR = CONFIG_DIR / "logs"

DEFAULT_MODEL = "qwen2.5:3b"

# Only these model families are permitted, and only under 14B parameters.
ALLOWED_FAMILIES = ("qwen", "gemma")
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*b", re.IGNORECASE)

DEFAULT_CONFIG: dict[str, Any] = {
    "model": DEFAULT_MODEL,
    "ollama_host": "http://127.0.0.1:11434",
    "temperature": 0.4,
    "context_window": 8192,
    "anonymous_mode": False,
    "tor_socks_proxy": "socks5h://127.0.0.1:9050",
    "safety": {
        "confirm_destructive_commands": True,
        "confirm_file_writes_outside_home": True,
        "max_command_timeout_seconds": 60,
        "denied_command_patterns": [
            r"rm\s+-rf\s+/(\s|$)",
            r"mkfs\.",
            r":\(\)\{.*\};:",  # fork bomb
            r"dd\s+if=.*of=/dev/(sd|nvme|hd)",
            r">\s*/dev/(sd|nvme|hd)",
            r"chmod\s+-R\s+000\s+/",
            r"chown\s+-R\s+.*\s+/(\s|$)",
        ],
    },
    "logging": {
        "level": "INFO",
        "streams": ["session", "tool", "error"],
        "max_bytes": 2_000_000,
        "backup_count": 5,
    },
}


def _model_family_and_size(model_name: str) -> tuple[str, float | None]:
    family = model_name.split(":")[0].split("-")[0].lower()
    match = _SIZE_RE.search(model_name)
    size = float(match.group(1)) if match else None
    return family, size


def validate_model(model_name: str) -> None:
    """Raise ValueError if the model is not an allowed Qwen/Gemma model <=14B."""
    family, size = _model_family_and_size(model_name)
    if not any(family.startswith(f) for f in ALLOWED_FAMILIES):
        raise ValueError(
            f"Model '{model_name}' rejected: only Qwen or Gemma family models are permitted."
        )
    if size is not None and size > 14:
        raise ValueError(
            f"Model '{model_name}' rejected: parameter size {size}B exceeds the 14B cap."
        )


@dataclass
class SafetyConfig:
    confirm_destructive_commands: bool = True
    confirm_file_writes_outside_home: bool = True
    max_command_timeout_seconds: int = 60
    denied_command_patterns: list[str] = field(default_factory=list)


@dataclass
class Settings:
    model: str = DEFAULT_MODEL
    ollama_host: str = "http://127.0.0.1:11434"
    temperature: float = 0.4
    context_window: int = 8192
    anonymous_mode: bool = False
    tor_socks_proxy: str = "socks5h://127.0.0.1:9050"
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    logging: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        if not CONFIG_FILE.exists():
            with CONFIG_FILE.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(DEFAULT_CONFIG, fh, sort_keys=False)
            data = DEFAULT_CONFIG
        else:
            with CONFIG_FILE.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            # Fill in any missing keys with defaults (forward-compatible upgrades).
            merged = {**DEFAULT_CONFIG, **data}
            merged["safety"] = {**DEFAULT_CONFIG["safety"], **data.get("safety", {})}
            merged["logging"] = {**DEFAULT_CONFIG["logging"], **data.get("logging", {})}
            data = merged

        validate_model(data.get("model", DEFAULT_MODEL))

        return cls(
            model=data.get("model", DEFAULT_MODEL),
            ollama_host=data.get("ollama_host", DEFAULT_CONFIG["ollama_host"]),
            temperature=float(data.get("temperature", DEFAULT_CONFIG["temperature"])),
            context_window=int(data.get("context_window", DEFAULT_CONFIG["context_window"])),
            anonymous_mode=bool(data.get("anonymous_mode", False)),
            tor_socks_proxy=data.get("tor_socks_proxy", DEFAULT_CONFIG["tor_socks_proxy"]),
            safety=SafetyConfig(**data.get("safety", DEFAULT_CONFIG["safety"])),
            logging=data.get("logging", DEFAULT_CONFIG["logging"]),
        )

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with CONFIG_FILE.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(
                {
                    "model": self.model,
                    "ollama_host": self.ollama_host,
                    "temperature": self.temperature,
                    "context_window": self.context_window,
                    "anonymous_mode": self.anonymous_mode,
                    "tor_socks_proxy": self.tor_socks_proxy,
                    "safety": self.safety.__dict__,
                    "logging": self.logging,
                },
                fh,
                sort_keys=False,
            )
