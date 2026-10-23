"""The one place in Owlgo that talks to a language model.

It speaks the OpenAI chat API, which Ollama, LM Studio, vLLM and most hosted
servers all understand, so moving from the local Qwen to a Kaggle GPU or
anywhere else only changes LLMSettings.
"""

import re
import time
from dataclasses import dataclass

from openai import OpenAI

from owlgo.config import LLMSettings

# A <think>...</think> block: reasoning the user must never see.
_THINK_BLOCK = re.compile(r"<think>(.*?)</think>", re.DOTALL)


@dataclass
class Reply:
    """One model reply, with any hidden reasoning kept separate."""

    # What the user sees.
    text: str
    # Hidden reasoning, if the model produced any. Never shown to users.
    thinking: str
    # "stop" means it finished; "length" means it hit max_tokens.
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    seconds: float


def split_thinking(content: str) -> tuple[str, str]:
    """Separate <think> blocks from the visible text. Returns (visible, thinking)."""
    thinking = [match.strip() for match in _THINK_BLOCK.findall(content)]
    visible = _THINK_BLOCK.sub("", content)
    # A reply cut off mid-thought leaves an unclosed <think>: hide everything after it.
    if "<think>" in visible:
        visible, _, rest = visible.partition("<think>")
        thinking.append(rest.strip())
    return visible.strip(), "\n".join(part for part in thinking if part)


class LLMClient:
    """Sends chat messages to the configured model."""

    def __init__(self, settings: LLMSettings | None = None):
        self.settings = settings or LLMSettings.from_env()
        self._client = OpenAI(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key,
            timeout=self.settings.timeout_seconds,
        )

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Reply:
        """Send messages ([{"role": ..., "content": ...}]) and return the reply."""
        settings = self.settings
        # Only send reasoning_effort when configured; some servers reject unknown options.
        extra = {"reasoning_effort": settings.reasoning_effort} if settings.reasoning_effort else {}
        start = time.perf_counter()
        response = self._client.chat.completions.create(
            model=settings.model,
            messages=messages,
            temperature=settings.temperature if temperature is None else temperature,
            max_tokens=settings.max_tokens if max_tokens is None else max_tokens,
            **extra,
        )
        seconds = time.perf_counter() - start
        choice = response.choices[0]
        visible, thinking = split_thinking(choice.message.content or "")
        # Some servers return reasoning in a separate field instead of <think> tags.
        fields = choice.message.model_extra or {}
        thinking = thinking or fields.get("reasoning") or fields.get("reasoning_content") or ""
        usage = response.usage
        return Reply(
            text=visible,
            thinking=thinking,
            finish_reason=choice.finish_reason or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            seconds=seconds,
        )
