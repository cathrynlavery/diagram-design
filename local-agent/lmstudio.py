#!/usr/bin/env python3
"""Minimal client for LM Studio's local OpenAI-compatible server.

Standard library only. Talks to `http://localhost:1234/v1` by default, streams
the completion so a multi-minute SVG generation never trips a read timeout,
and strips the `<think>…</think>` reasoning block that Qwen-family models
emit before their answer.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from typing import Callable, Iterator

DEFAULT_BASE_URL = "http://localhost:1234/v1"
THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class LMStudioError(RuntimeError):
    pass


class LMStudio:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str | None = None,
        timeout: int = 900,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # -- discovery ---------------------------------------------------------

    def _get(self, path: str) -> dict:
        request = urllib.request.Request(self.base_url + path)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise LMStudioError(
                f"cannot reach LM Studio at {self.base_url}: {exc.reason}. "
                "Start the server in LM Studio (Developer tab → Start Server)."
            ) from exc

    def models(self) -> list[str]:
        return [entry["id"] for entry in self._get("/models").get("data", [])]

    def model_info(self, model: str) -> dict | None:
        """LM Studio's richer /api/v0/models entry, if that API is enabled."""
        root = self.base_url[: -len("/v1")] if self.base_url.endswith("/v1") else self.base_url
        try:
            request = urllib.request.Request(root + "/api/v0/models")
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError):
            return None
        for entry in data.get("data", []):
            if entry.get("id") == model:
                return entry
        return None

    def resolve_model(self) -> str:
        available = self.models()
        if not available:
            raise LMStudioError("LM Studio lists no models; download one in the app first")
        if self.model is None:
            self.model = available[0]
        elif self.model not in available:
            raise LMStudioError(
                f"model {self.model!r} is not available; LM Studio lists: "
                + ", ".join(available)
            )
        return self.model

    # -- completion --------------------------------------------------------

    def _stream(self, payload: dict) -> Iterator[str]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise LMStudioError(f"LM Studio returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LMStudioError(f"cannot reach LM Studio at {self.base_url}: {exc.reason}") from exc
        with response:
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                for choice in event.get("choices", []):
                    delta = choice.get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yield text

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int | None = 16384,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        payload: dict = {
            "model": self.resolve_model(),
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        chunks: list[str] = []
        for text in self._stream(payload):
            chunks.append(text)
            if on_token:
                on_token(text)
        return strip_thinking("".join(chunks))


def strip_thinking(text: str) -> str:
    text = THINK_RE.sub("", text)
    # An unterminated block means the model ran out of tokens while thinking.
    if "<think>" in text and "</think>" not in text:
        return ""
    return text.strip()


def progress_printer(prefix: str = "") -> Callable[[str], None]:
    """Prints a dot per ~200 streamed characters, so long runs show life."""
    state = {"chars": 0, "dots": 0}

    def on_token(text: str) -> None:
        state["chars"] += len(text)
        wanted = state["chars"] // 200
        if wanted > state["dots"]:
            sys.stderr.write("." * (wanted - state["dots"]))
            sys.stderr.flush()
            state["dots"] = wanted

    if prefix:
        sys.stderr.write(prefix)
        sys.stderr.flush()
    return on_token
