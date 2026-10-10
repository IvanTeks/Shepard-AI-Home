from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, timeout_seconds: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama returned HTTP {exc.code}: {body}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OllamaError(f"Cannot reach Ollama at {self.base_url}: {exc}") from exc

    def list_models(self) -> list[str]:
        response = self._request("GET", "/api/tags")
        return [str(model.get("name")) for model in response.get("models", []) if model.get("name")]

    def chat(self, model: str, messages: list[dict[str, str]], *, json_mode: bool = False,
             temperature: float = 0.2, num_predict: int = 1400) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": temperature, "num_predict": num_predict},
        }
        if json_mode:
            payload["format"] = "json"
        response = self._request("POST", "/api/chat", payload)
        try:
            return str(response["message"]["content"]).strip()
        except (KeyError, TypeError) as exc:
            raise OllamaError(f"Unexpected Ollama response: {response}") from exc
