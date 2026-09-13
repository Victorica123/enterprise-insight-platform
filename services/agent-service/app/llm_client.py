"""Shared, bounded LLM client access.

The OpenAI-compatible SDK client owns a reusable HTTP connection pool.  Keeping
client construction here also gives every LLM call the same timeout, retry and
output-budget policy instead of letting individual agents drift.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from types import SimpleNamespace
from typing import Any

from app.call_limits import acquire_call
from app.chat_events import ChatEventSink, current_event_sink
from app.config import LLMSettings, get_llm_settings
from app.model_egress import require_model_egress_allowed


@lru_cache(maxsize=4)
def _build_client(settings: LLMSettings):
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - installation failure
        raise RuntimeError(
            "未安装 openai 依赖，请先运行 pip install -r requirements.txt。"
        ) from exc

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
    response_format: dict[str, Any] | None = None,
    purpose: str = "",
) -> Any:
    """One bounded chat completion; ``purpose`` labels the call in the request budget."""
    require_model_egress_allowed()
    settings = get_llm_settings()
    if not settings.api_key:
        raise RuntimeError(f"未配置 {settings.provider} API Key。")
    # 阶段 0.4 每请求模型调用上限：只有真正要出网的调用才消耗预算；
    # 未绑定请求（后台任务、单元测试）不受限。超限抛 CallLimitExceeded，由调用方降级。
    acquire_call("model", label=purpose)

    sink = current_event_sink()
    if sink is not None and purpose == "answer":
        return sink.wait(asyncio.run_coroutine_threadsafe(
            _async_stream_completion(settings, messages, temperature, sink), sink.loop,
        ))

    client = _build_client(settings)
    request: dict[str, Any] = {
        "model": settings.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": settings.max_completion_tokens,
        "stream": False,
    }
    if response_format is not None:
        request["response_format"] = response_format
    return client.chat.completions.create(**request)


_ASYNC_CLIENTS: dict[tuple[LLMSettings, asyncio.AbstractEventLoop], Any] = {}


async def _async_stream_completion(settings: LLMSettings, messages: list[dict[str, str]],
                                   temperature: float, sink: ChatEventSink) -> Any:
    from openai import AsyncOpenAI

    key = settings, asyncio.get_running_loop()
    client = _ASYNC_CLIENTS.get(key)
    if client is None:
        client = AsyncOpenAI(api_key=settings.api_key, base_url=settings.base_url,
                             timeout=settings.timeout_seconds, max_retries=settings.max_retries)
        _ASYNC_CLIENTS[key] = client
    chunks: list[str] = []
    usage = None
    # Bound the entire stream too; an upstream that trickles forever must not
    # keep a conversation lease or worker occupied indefinitely.
    async with asyncio.timeout(settings.timeout_seconds * (settings.max_retries + 1)):
        stream = await client.chat.completions.create(
            model=settings.model, messages=messages, temperature=temperature,
            max_tokens=settings.max_completion_tokens, stream=True,
            stream_options={"include_usage": True},
        )
        try:
            async for chunk in stream:
                sink.check()
                if getattr(chunk, "usage", None) is not None:
                    usage = chunk.usage
                if chunk.choices:
                    content = chunk.choices[0].delta.content
                    if isinstance(content, str) and content:
                        chunks.append(content)
                        await sink.aemit("delta", {"text": content, "provisional": True})
        finally:
            await stream.close()
    if not chunks:
        raise RuntimeError("Model stream returned no text.")
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="".join(chunks)))], usage=usage)


async def close_async_llm_clients() -> None:
    loop = asyncio.get_running_loop()
    for key in [key for key in _ASYNC_CLIENTS if key[1] is loop]:
        await _ASYNC_CLIENTS.pop(key).close()


def clear_llm_client_cache() -> None:
    """Test/deployment hook for credential rotation."""
    _build_client.cache_clear()
