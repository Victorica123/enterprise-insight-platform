"""Shared, bounded LLM client access.

The OpenAI-compatible SDK client owns a reusable HTTP connection pool.  Keeping
client construction here also gives every LLM call the same timeout, retry and
output-budget policy instead of letting individual agents drift.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.config import LLMSettings, get_llm_settings


@lru_cache(maxsize=4)
def _build_client(settings: LLMSettings):
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - installation failure
        raise RuntimeError("未安装 openai 依赖，请先运行 pip install -r requirements.txt。") from exc

    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


def create_chat_completion(
    *,
    messages: list[dict[str, str]],
    temperature: float,
) -> Any:
    settings = get_llm_settings()
    if not settings.api_key:
        raise RuntimeError(f"未配置 {settings.provider} API Key。")

    client = _build_client(settings)
    return client.chat.completions.create(
        model=settings.model,
        messages=messages,
        temperature=temperature,
        max_tokens=settings.max_completion_tokens,
        stream=False,
    )


def clear_llm_client_cache() -> None:
    """Test/deployment hook for credential rotation."""
    _build_client.cache_clear()
