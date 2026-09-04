"""Free-tier-first provider adapters: Groq (OpenAI-compatible) and Google
Gemini. Both are thin HTTP clients — no vendor SDKs to keep the footprint
small and the retry behavior our own."""

import httpx

from app.llm.base import LLMError

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class GroqProvider:
    name = "groq"
    _url = "https://api.groq.com/openai/v1/chat/completions"
    _default_model = "openai/gpt-oss-120b"
    _fallback_models = ["qwen/qwen3.6-27b", "groq/compound"]

    def __init__(self, api_key: str, model: str = "", transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise LLMError("Groq API key missing (set LLM_API_KEY)")
        self._api_key = api_key
        self._model = model or self._default_model
        self._client = httpx.Client(timeout=_TIMEOUT, transport=transport)

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        models_to_try = [self._model] + [m for m in self._fallback_models if m != self._model]
        last_error = ""
        for model in models_to_try:
            for use_json_mode in (True, False):
                payload: dict = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                }
                if use_json_mode:
                    payload["response_format"] = {"type": "json_object"}
                resp = self._client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                if resp.status_code == 200:
                    try:
                        return resp.json()["choices"][0]["message"]["content"]
                    except (KeyError, IndexError, ValueError) as exc:
                        raise LLMError(f"Unexpected Groq response shape: {exc}") from exc
                elif resp.status_code == 400 and use_json_mode:
                    continue  # Retry this model without response_format if unsupported
                last_error = f"Groq API {resp.status_code}: {resp.text[:300]}"
                break
        raise LLMError(last_error)


class GeminiProvider:
    name = "gemini"
    _default_model = "gemini-2.0-flash"

    def __init__(self, api_key: str, model: str = "", transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise LLMError("Gemini API key missing (set LLM_API_KEY)")
        self._api_key = api_key
        self._model = model or self._default_model
        self._client = httpx.Client(timeout=_TIMEOUT, transport=transport)

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent"
        )
        resp = self._client.post(
            url,
            params={"key": self._api_key},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
            },
        )
        if resp.status_code != 200:
            raise LLMError(f"Gemini API {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Unexpected Gemini response shape: {exc}") from exc


def get_provider(name: str, api_key: str, model: str = ""):
    providers = {"groq": GroqProvider, "gemini": GeminiProvider}
    if name not in providers:
        raise LLMError(f"Unknown LLM provider {name!r}; choose one of {sorted(providers)}")
    return providers[name](api_key=api_key, model=model)
