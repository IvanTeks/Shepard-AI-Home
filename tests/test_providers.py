import json
import unittest

from shepard.providers import AnthropicClient, GeminiClient, provider_model_name


class _Response:
    def __init__(self, value):
        self.body = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


class _Opener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return _Response(self.responses.pop(0))


class AnthropicProviderTests(unittest.TestCase):
    def test_lists_models_and_sends_messages(self):
        opener = _Opener([
            {"data": [{"id": "claude-sonnet-5"}, {"id": "claude-haiku-4-5-20251001"}]},
            {"content": [{"type": "text", "text": "{\"reply\":\"Ready\"}"}]},
        ])
        client = AnthropicClient("test-api-key-long-enough", 17, opener=opener)

        self.assertEqual(client.list_models(), ["claude-sonnet-5", "claude-haiku-4-5-20251001"])
        reply = client.chat(
            "claude-sonnet-5",
            [
                {"role": "system", "content": "You are Shepard."},
                {"role": "user", "content": "Answer."},
            ],
            json_mode=True,
            num_predict=600,
        )

        self.assertEqual(reply, '{"reply":"Ready"}')
        request = opener.requests[-1][0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(payload["model"], "claude-sonnet-5")
        self.assertEqual(payload["max_tokens"], 600)
        self.assertIn("valid JSON object", payload["system"])
        self.assertEqual(payload["messages"], [{"role": "user", "content": "Answer."}])

    def test_provider_prefix_is_removed(self):
        self.assertEqual(provider_model_name("claude:claude-sonnet-5"), "claude-sonnet-5")
        self.assertEqual(provider_model_name("qwen3:8b"), "qwen3:8b")


class GeminiProviderTests(unittest.TestCase):
    def test_lists_generate_models_and_sends_messages(self):
        opener = _Opener([
            {"models": [
                {"name": "models/gemini-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/text-embedding", "supportedGenerationMethods": ["embedContent"]},
            ]},
            {"candidates": [{"content": {"parts": [{"text": "{\"reply\":\"Ready\"}"}]}}]},
        ])
        client = GeminiClient("test-gemini-key-long-enough", 19, opener=opener)

        self.assertEqual(client.list_models(), ["gemini-flash"])
        reply = client.chat(
            "gemini-flash",
            [
                {"role": "system", "content": "You are Shepard."},
                {"role": "user", "content": "Answer."},
            ],
            json_mode=True,
            num_predict=700,
        )

        self.assertEqual(reply, '{"reply":"Ready"}')
        request = opener.requests[-1][0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            request.full_url,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash:generateContent",
        )
        self.assertEqual(request.get_header("X-goog-api-key"), "test-gemini-key-long-enough")
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "You are Shepard.")

    def test_provider_prefix_is_removed(self):
        self.assertEqual(provider_model_name("gemini:gemini-flash"), "gemini-flash")


if __name__ == "__main__":
    unittest.main()
