"""Provider-agnostic LLM interface. Engines depend on this protocol only;
which vendor answers is a config value (`LLM_PROVIDER`), never a code change."""

from typing import Protocol


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        """Return the model's text completion for a system+user prompt."""
        ...


class LLMError(RuntimeError):
    """Raised for provider/API failures so callers can retry or mark FAILED."""
