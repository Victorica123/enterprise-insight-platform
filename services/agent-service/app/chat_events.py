"""Bounded SSE delivery and cooperative cancellation for the shared chat pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from concurrent.futures import CancelledError, Future
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from datetime import UTC, datetime
from threading import Event, Lock

from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


class ChatCancelled(BaseException):
    """Like asyncio.CancelledError, cancellation must bypass provider fallbacks."""


class ChatEventSink:
    def __init__(self, loop: asyncio.AbstractEventLoop, conversation_id: str | None, exchange_id: str):
        self.loop = loop
        self.conversation_id = conversation_id
        self.exchange_id = exchange_id
        self.queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=64)
        self.cancelled = Event()
        self.has_deltas = False
        self._pending: set[Future] = set()
        self._lock = Lock()

    def envelope(self, kind: str, content: object) -> dict:
        return {"type": kind, "content": content, "timestamp": datetime.now(UTC).isoformat(),
                "conversation_id": self.conversation_id, "exchange_id": self.exchange_id}

    def check(self):
        if self.cancelled.is_set():
            raise ChatCancelled()

    def wait(self, future: Future):
        with self._lock:
            self._pending.add(future)
        try:
            while True:
                self.check()
                try:
                    return future.result(timeout=0.25)
                except FutureTimeout:
                    if future.done():
                        raise
                    continue
                except CancelledError as exc:
                    raise ChatCancelled() from exc
        finally:
            if self.cancelled.is_set():
                future.cancel()
            with self._lock:
                self._pending.discard(future)

    def emit(self, kind: str, content: object):
        self.check()
        self.wait(asyncio.run_coroutine_threadsafe(self.aemit(kind, content), self.loop))

    async def aemit(self, kind: str, content: object):
        self.check()
        if kind == "delta":
            self.has_deltas = True
        await self.queue.put(self.envelope(kind, content))

    def cancel(self):
        self.cancelled.set()
        with self._lock:
            for future in tuple(self._pending):
                future.cancel()


_SINK: ContextVar[ChatEventSink | None] = ContextVar("chat_event_sink", default=None)
_GUARD: ContextVar[Callable | None] = ContextVar("chat_lease_guard", default=None)


def current_event_sink() -> ChatEventSink | None:
    return _SINK.get()


def check_chat_cancelled() -> None:
    guard = _GUARD.get()
    if guard is not None:
        guard()
    sink = _SINK.get()
    if sink is not None:
        sink.check()


def emit_chat_event(kind: str, content: object) -> None:
    sink = _SINK.get()
    if sink is not None:
        sink.emit(kind, content)


@contextmanager
def bind_chat_guard(guard: Callable):
    token = _GUARD.set(guard)
    try:
        yield
    finally:
        _GUARD.reset(token)


@contextmanager
def bind_event_sink(sink: ChatEventSink):
    token = _SINK.set(sink)
    try:
        yield
    finally:
        _SINK.reset(token)


def encode_sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def stream_chat_events(run: Callable, *, conversation_id: str | None, exchange_id: str):
    sink = ChatEventSink(asyncio.get_running_loop(), conversation_id, exchange_id)

    def produce():
        with bind_event_sink(sink):
            try:
                response = run()
                sink.check()
                if not sink.has_deltas:
                    for start in range(0, len(response.answer), 96):
                        sink.emit("delta", {"text": response.answer[start:start + 96], "provisional": True})
                sink.emit("sources", [source.model_dump(mode="json") for source in response.sources])
                sink.emit("follow_up", response.follow_up)
                sink.emit("done", response.model_dump(mode="json"))
            except ChatCancelled:
                pass
            except Exception:
                logger.exception("chat_stream_failed")
                if not sink.cancelled.is_set():
                    sink.emit("error", {"message": "本次问答未完成，请稍后重试。"})
            finally:
                if not sink.cancelled.is_set():
                    sink.wait(asyncio.run_coroutine_threadsafe(sink.queue.put(None), sink.loop))

    worker = asyncio.create_task(run_in_threadpool(produce))
    try:
        yield encode_sse(sink.envelope("stage", {"name": "preparation", "status": "running", "detail": "正在准备问题与授权证据。"}))
        while True:
            try:
                event = await asyncio.wait_for(sink.queue.get(), timeout=15)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if event is None:
                break
            yield encode_sse(event)
        await worker
    finally:
        sink.cancel()
        # Let even a not-yet-started worker enter execute_chat's finally block,
        # so an early disconnect refunds the durable reservation. Cancellation
        # closes the provider stream; blocking non-stream steps remain bounded.
        with suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(asyncio.shield(worker), timeout=1)
