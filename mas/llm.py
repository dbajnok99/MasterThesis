"""Pick the right LLM client based on the model name.

Supported providers and naming conventions:
  - Anthropic:  "claude-*"                      (needs ANTHROPIC_API_KEY)
  - DeepSeek:   "deepseek-chat", "deepseek-reasoner"  (needs DEEPSEEK_API_KEY)
  - Ollama:     "ollama:<tag>", e.g. "ollama:llama3.1:8b"  (free, local)
  - OpenAI:     everything else, e.g. "gpt-4o"   (needs OPENAI_API_KEY)

Ollama and DeepSeek both speak the OpenAI chat-completions protocol, so they
reuse the OpenAI client/chat-model with a different base_url and api_key.
"""
from __future__ import annotations

import config as cfg

OLLAMA_PREFIX = "ollama:"


def _is_anthropic(model: str) -> bool:
    return model.startswith("claude-")


def _is_ollama(model: str) -> bool:
    return model.startswith(OLLAMA_PREFIX)


def _is_deepseek(model: str) -> bool:
    return model.startswith("deepseek-")


def _ollama_tag(model: str) -> str:
    """Strip the 'ollama:' prefix, leaving the bare tag (which may contain ':')."""
    return model[len(OLLAMA_PREFIX):]


def _openai_compatible_params(model: str) -> dict:
    """base_url / api_key / model for any OpenAI-protocol provider."""
    if _is_ollama(model):
        return {"model": _ollama_tag(model),
                "base_url": cfg.OLLAMA_BASE_URL,
                "api_key": "ollama"}
    if _is_deepseek(model):
        return {"model": model,
                "base_url": cfg.DEEPSEEK_BASE_URL,
                "api_key": cfg.DEEPSEEK_API_KEY}
    return {"model": model,
            "base_url": None,
            "api_key": cfg.OPENAI_API_KEY}


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

    from langchain_openai import ChatOpenAI
    params = _openai_compatible_params(model)
    return ChatOpenAI(
        model=params["model"],
        api_key=params["api_key"],
        base_url=params["base_url"],
        max_tokens=cfg.MAX_TOKENS,
    )


def make_raw_client(model: str | None = None):
    """Return a thin wrapper around the provider SDK for non-tool LLM calls."""
    model = model or cfg.MODEL
    if _is_anthropic(model):
        return _AnthropicClient(model)
    return _OpenAIClient(model)


# provider wrappers

class _OpenAIClient:
    """Wraps openai.OpenAI with a unified call interface.

    Also serves Ollama and DeepSeek via their OpenAI-compatible endpoints.
    """

    def __init__(self, model: str):
        from openai import OpenAI
        params = _openai_compatible_params(model)
        self.model = params["model"]
        self._client = OpenAI(api_key=params["api_key"], base_url=params["base_url"])

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
