"""Pick the right LLM client based on the model name (OpenAI or Anthropic)."""
from __future__ import annotations

import config as cfg


def _is_anthropic(model: str) -> bool:
    return model.startswith("claude-")


def make_chat_model(model: str | None = None):
    """Return a LangChain chat model for the given model name."""
    model = model or cfg.MODEL
    if _is_anthropic(model):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            api_key=cfg.ANTHROPIC_API_KEY,
            max_tokens=cfg.MAX_TOKENS,
        )
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=cfg.OPENAI_API_KEY,
            max_tokens=cfg.MAX_TOKENS,
        )


def make_raw_client(model: str | None = None):
    """Return a thin wrapper around the provider SDK for non-tool LLM calls."""
    model = model or cfg.MODEL
    if _is_anthropic(model):
        return _AnthropicClient(model)
    else:
        return _OpenAIClient(model)


# provider wrappers

class _OpenAIClient:
    """Wraps openai.OpenAI with a unified call interface."""

    def __init__(self, model: str):
        from openai import OpenAI
        self.model = model
        self._client = OpenAI(api_key=cfg.OPENAI_API_KEY)

    def complete(self, messages: list[dict], max_tokens: int = cfg.MAX_TOKENS) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
        )
        return resp.choices[0].message.content or ""


class _AnthropicClient:
    """Wraps anthropic.Anthropic with a unified call interface."""

    def __init__(self, model: str):
        from anthropic import Anthropic
        self.model = model
        self._client = Anthropic(api_key=cfg.ANTHROPIC_API_KEY)

    def complete(self, messages: list[dict], max_tokens: int = cfg.MAX_TOKENS) -> str:
        system = ""
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                user_messages.append(m)
        kwargs: dict = dict(
            model=self.model,
            max_tokens=max_tokens,
            messages=user_messages,
        )
        if system:
            kwargs["system"] = system
        resp = self._client.messages.create(**kwargs)
        return resp.content[0].text if resp.content else ""
