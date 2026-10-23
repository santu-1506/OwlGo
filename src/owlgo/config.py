"""Settings for talking to a model. Swapping models means changing config, never code.

Every setting can be overridden with an environment variable named
OWLGO_LLM_<SETTING>, for example:

    OWLGO_LLM_MODEL=qwen3.5:9b
    OWLGO_LLM_BASE_URL=http://localhost:11434/v1    # Ollama's OpenAI-compatible API
    OWLGO_LLM_API_KEY=...                           # needed by hosted servers, ignored by Ollama
"""

import os
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class LLMSettings:
    """Where the model lives and how to call it."""

    # Any OpenAI-compatible server. The default is the local Ollama.
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen3.5:9b"
    # Ollama ignores the key, but the OpenAI SDK insists on having one.
    api_key: str = "ollama"
    # Low temperature: debugging help should be steady, not creative.
    temperature: float = 0.3
    max_tokens: int = 400
    # "none" turns Qwen's thinking off on Ollama's OpenAI endpoint ("think": false is
    # ignored there). An empty value sends nothing, for servers without the option.
    reasoning_effort: str = "none"
    timeout_seconds: float = 300.0

    @classmethod
    def from_env(cls) -> "LLMSettings":
        """Defaults, overridden by any OWLGO_LLM_* environment variables."""
        values = {}
        for field in fields(cls):
            raw = os.environ.get(f"OWLGO_LLM_{field.name.upper()}")
            if raw is not None:
                # Convert to the field's type (float or int); strings stay as they are.
                values[field.name] = field.type(raw) if field.type in (float, int) else raw
        return cls(**values)
