"""Клиент строго локального llama.cpp; внешние адреса запрещены."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from authoroved_core.core.qwen_shadow import ProviderCompletion


class LocalQwenError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalQwenConfig:
    endpoint: str = "http://127.0.0.1:8089"
    model_name: str = "Qwen3-8B-GGUF"
    model_sha256: str = ""
    runtime_version: str = ""
    seed: int = 20260914
    maximum_output_tokens: int = 768
    timeout_seconds: int = 300
    api_key: str = field(default="", repr=False)

    def __post_init__(self):
        parsed = urlparse(self.endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Qwen разрешён только через локальный HTTP-адрес.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Локальный адрес Qwen не должен содержать учётные данные или параметры.")
        if parsed.path not in {"", "/"}:
            raise ValueError("В локальном адресе Qwen не должен быть задан путь.")


class LlamaCppLocalProvider:
    def __init__(self, config: LocalQwenConfig):
        self.config = config

    def complete(self, *, system_prompt: str, user_prompt: str,
                 response_schema: dict[str, Any]) -> ProviderCompletion:
        payload = {
            "model": self.config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "top_k": 1,
            "top_p": 1,
            "seed": self.config.seed,
            "max_tokens": self.config.maximum_output_tokens,
            "stream": False,
            "cache_prompt": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "authoroved_candidates", "strict": True,
                                "schema": response_schema},
            },
        }
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = Request(
            self.config.endpoint.rstrip("/") + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers, method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, UnicodeError, json.JSONDecodeError) as exc:
            raise LocalQwenError("Локальный сервер Qwen не вернул корректный ответ.") from exc
        try:
            raw = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalQwenError("В ответе локального сервера отсутствует content.") from exc
        if not isinstance(raw, str):
            raise LocalQwenError("Поле content локального сервера должно быть строкой.")
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        return ProviderCompletion(raw, {
            "provider": "llama.cpp local",
            "endpoint": self.config.endpoint,
            "model_name": self.config.model_name,
            "model_sha256": self.config.model_sha256,
            "runtime_version": self.config.runtime_version,
            "seed": self.config.seed,
            "temperature": 0,
            "top_k": 1,
            "top_p": 1,
            "cache_prompt": False,
            "usage": usage,
        })
