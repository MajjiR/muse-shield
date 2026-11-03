"""Minimal OpenAI-compatible chat client (Ollama, llama-server, Llama API, ...)."""

from __future__ import annotations

from typing import Any

import httpx


class LLMError(RuntimeError):
    pass


def chat(
    client: httpx.Client,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    api_key: str = "",
    json_mode: bool = False,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    timeout: float = 60.0,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        resp = client.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise LLMError(str(exc)) from exc
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"unexpected response shape: {data!r:.200}") from exc
