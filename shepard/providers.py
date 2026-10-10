from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import Settings
from .ollama import OllamaClient


ANTHROPIC_API_BASE = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class AnthropicError(RuntimeError):
    pass


class GeminiError(RuntimeError):
    pass


def _trusted_ssl_context() -> ssl.SSLContext:
    candidates = [
        ssl.get_default_verify_paths().cafile,
        "/etc/ssl/cert.pem",
        "/opt/homebrew/etc/openssl@3/cert.pem",
        "/usr/local/etc/openssl@3/cert.pem",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


class AnthropicClient:
    def __init__(self, api_key: str, timeout_seconds: int = 300, opener: Any | None = None):
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self.opener = opener or urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=_trusted_ssl_context())
        )
        if not self.api_key:
            raise AnthropicError("Claude API key is not configured")

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            ANTHROPIC_API_BASE + path,
            data=body,
            method="GET" if body is None else "POST",
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "user-agent": "Shepard-Labyrinth/0.3",
            },
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                value = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
            except (json.JSONDecodeError, AttributeError):
                detail = ""
            raise AnthropicError(detail or f"Claude API request failed ({exc.code})") from exc
        except urllib.error.URLError as exc:
            raise AnthropicError("Claude API could not be reached") from exc
        except json.JSONDecodeError as exc:
            raise AnthropicError("Claude API returned an unreadable response") from exc
        if not isinstance(value, dict):
            raise AnthropicError("Claude API returned an unexpected response")
        return value

    def list_models(self) -> list[str]:
        value = self._request("/v1/models?limit=100")
        return [str(item["id"]) for item in value.get("data", []) if isinstance(item, dict) and item.get("id")]

    def chat(self, model: str, messages: list[dict[str, str]], *, json_mode: bool = False,
             temperature: float = 0.2, num_predict: int = 1400) -> str:
        del temperature  # Newer Claude models may reject non-default temperature values.
        system_parts = [message["content"] for message in messages if message.get("role") == "system"]
        if json_mode:
            system_parts.append("Return exactly one valid JSON object and no surrounding prose or fences.")
        conversation = [
            {"role": message["role"], "content": message["content"]}
            for message in messages if message.get("role") in {"user", "assistant"}
        ]
        if not conversation:
            raise AnthropicError("Claude needs at least one user or assistant message")
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max(1, min(int(num_predict), 8192)),
            "messages": conversation,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        value = self._request("/v1/messages", payload)
        parts = [
            str(block.get("text", "")) for block in value.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        answer = "".join(parts).strip()
        if not answer:
            raise AnthropicError("Claude returned no text")
        return answer


class GeminiClient:
    def __init__(self, api_key: str, timeout_seconds: int = 300, opener: Any | None = None):
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self.opener = opener or urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=_trusted_ssl_context())
        )
        if not self.api_key:
            raise GeminiError("Gemini API key is not configured")

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            GEMINI_API_BASE + path,
            data=body,
            method="GET" if body is None else "POST",
            headers={
                "content-type": "application/json",
                "x-goog-api-key": self.api_key,
                "user-agent": "Shepard-Labyrinth/0.3",
            },
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                value = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
            except (json.JSONDecodeError, AttributeError):
                detail = ""
            raise GeminiError(detail or f"Gemini API request failed ({exc.code})") from exc
        except urllib.error.URLError as exc:
            raise GeminiError("Gemini API could not be reached") from exc
        except json.JSONDecodeError as exc:
            raise GeminiError("Gemini API returned an unreadable response") from exc
        if not isinstance(value, dict):
            raise GeminiError("Gemini API returned an unexpected response")
        return value

    def list_models(self) -> list[str]:
        value = self._request("/models?pageSize=100")
        models: list[str] = []
        for item in value.get("models", []):
            if not isinstance(item, dict):
                continue
            methods = item.get("supportedGenerationMethods", [])
            name = str(item.get("name", "")).removeprefix("models/")
            if name and "generateContent" in methods:
                models.append(name)
        return models

    def chat(self, model: str, messages: list[dict[str, str]], *, json_mode: bool = False,
             temperature: float = 0.2, num_predict: int = 1400) -> str:
        system_parts = [message["content"] for message in messages if message.get("role") == "system"]
        contents = [
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
            for message in messages if message.get("role") in {"user", "assistant"}
        ]
        if not contents:
            raise GeminiError("Gemini needs at least one user or assistant message")
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": float(temperature),
                "maxOutputTokens": max(1, min(int(num_predict), 8192)),
            },
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        value = self._request(f"/models/{model}:generateContent", payload)
        candidates = value.get("candidates", [])
        if not candidates:
            raise GeminiError("Gemini returned no response")
        content = candidates[0].get("content", {}) if isinstance(candidates[0], dict) else {}
        answer = "".join(
            str(part.get("text", "")) for part in content.get("parts", [])
            if isinstance(part, dict)
        ).strip()
        if not answer:
            raise GeminiError("Gemini returned no text")
        return answer


def anthropic_secret_path(settings: Settings) -> Path:
    return settings.project_root / "secrets" / "anthropic.json"


def load_anthropic_api_key(settings: Settings) -> str:
    environment_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if environment_key:
        return environment_key
    path = anthropic_secret_path(settings)
    if not path.is_file():
        return ""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(value.get("api_key", "")).strip() if isinstance(value, dict) else ""


def gemini_secret_path(settings: Settings) -> Path:
    return settings.project_root / "secrets" / "gemini.json"


def load_gemini_api_key(settings: Settings) -> str:
    environment_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if environment_key:
        return environment_key
    path = gemini_secret_path(settings)
    if not path.is_file():
        return ""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(value.get("api_key", "")).strip() if isinstance(value, dict) else ""


def is_claude_model(model: str) -> bool:
    return model.startswith("claude:") or model.startswith("anthropic:")


def is_gemini_model(model: str) -> bool:
    return model.startswith("gemini:") or model.startswith("google:")


def is_external_model(model: str) -> bool:
    return is_claude_model(model) or is_gemini_model(model)


def provider_model_name(model: str) -> str:
    return model.split(":", 1)[1] if is_external_model(model) else model


def chat_with_model(settings: Settings, model: str, messages: list[dict[str, str]], *,
                    json_mode: bool = False, temperature: float = 0.2,
                    num_predict: int = 1400) -> str:
    if is_claude_model(model):
        return AnthropicClient(
            load_anthropic_api_key(settings), settings.ollama_timeout_seconds
        ).chat(
            provider_model_name(model), messages, json_mode=json_mode,
            temperature=temperature, num_predict=num_predict,
        )
    if is_gemini_model(model):
        return GeminiClient(
            load_gemini_api_key(settings), settings.ollama_timeout_seconds
        ).chat(
            provider_model_name(model), messages, json_mode=json_mode,
            temperature=temperature, num_predict=num_predict,
        )
    return OllamaClient(
        settings.ollama_base_url, settings.ollama_timeout_seconds
    ).chat(
        model, messages, json_mode=json_mode,
        temperature=temperature, num_predict=num_predict,
    )
