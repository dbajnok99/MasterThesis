"""
Spotlighting via encoding (Hines et al. 2024, Section 3.4). Untrusted content
is base64-encoded before it reaches the model, which makes the boundary
between data and instructions unmistakable, unlike a plain <data> delimiter
that an attacker could simply include in their payload. The paper found
encoding to be its most effective variant, ahead of delimiting and
datamarking, though it recommends restricting it to high-capacity models
since weaker ones struggle to decode reliably.
"""
from __future__ import annotations

import base64

from langchain_core.tools import StructuredTool


def encode(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def spotlight_tools(tools: list) -> list:
    """Wrap each tool so its output is base64-encoded before the model sees it."""
    wrapped = []
    for t in tools:
        original = t.func

        def _make_wrapper(fn):
            def wrapper(*args, **kwargs):
                return encode(str(fn(*args, **kwargs)))
            return wrapper

        wrapped.append(StructuredTool.from_function(
            func=_make_wrapper(original),
            name=t.name,
            description=t.description,
            args_schema=t.args_schema,
        ))
    return wrapped
