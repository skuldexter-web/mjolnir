"""
mjolnir.llm.client
-------------------
Thin wrapper around the local Ollama REST API. No cloud providers,
no API keys, no telemetry. Supports optional anonymous mode routing
requests through a local Tor SOCKS proxy via torsocks-compatible
session configuration.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from typing import Any

import requests

from mjolnir.config.settings import Settings, validate_model

logger = logging.getLogger("mjolnir.llm")


class OllamaError(RuntimeError):
    """Raised when the local Ollama server cannot be reached or errors out."""


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        validate_model(settings.model)
        self.session = requests.Session()
        if settings.anonymous_mode:
            self.session.proxies.update(
                {"http": settings.tor_socks_proxy, "https": settings.tor_socks_proxy}
            )
            logger.info("Anonymous mode enabled: routing Ollama traffic via %s", settings.tor_socks_proxy)

    def health_check(self) -> bool:
        try:
            resp = self.session.get(f"{self.settings.ollama_host}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def ensure_model_available(self) -> bool:
        try:
            resp = self.session.get(f"{self.settings.ollama_host}/api/tags", timeout=10)
            resp.raise_for_status()
            tags = [m["name"] for m in resp.json().get("models", [])]
            return self.settings.model in tags
        except requests.RequestException as exc:
            raise OllamaError(f"Could not reach Ollama at {self.settings.ollama_host}: {exc}") from exc

    def pull_model(self) -> Generator[str, None, None]:
        payload = {"name": self.settings.model, "stream": True}
        try:
            with self.session.post(
                f"{self.settings.ollama_host}/api/pull", json=payload, stream=True, timeout=None
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if "status" in data:
                        yield data["status"]
        except requests.RequestException as exc:
            raise OllamaError(f"Model pull failed: {exc}") from exc

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Stream a chat completion from Ollama. Yields raw JSON chunks."""
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.settings.temperature,
                "num_ctx": self.settings.context_window,
            },
        }
        if tools:
            payload["tools"] = tools

        try:
            with self.session.post(
                f"{self.settings.ollama_host}/api/chat", json=payload, stream=True, timeout=None
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    yield json.loads(line)
        except requests.RequestException as exc:
            raise OllamaError(f"Chat request failed: {exc}") from exc

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Non-streaming convenience wrapper, returns the final assembled message."""
        content = ""
        final: dict[str, Any] = {}
        for chunk in self.chat_stream(messages, tools=tools):
            final = chunk
            msg = chunk.get("message", {})
            content += msg.get("content", "")
        final.setdefault("message", {})["content"] = content
        return final
