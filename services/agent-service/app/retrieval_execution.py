"""Deadline-limited retrieval on separate, bounded process-wide worker pools.

A timed-out native inference cannot be killed by Python. It retains its slot
until it finishes; subsequent work fails fast when that channel is saturated.
There is no unbounded executor queue and no replacement pool per request.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextvars import copy_context
from dataclasses import dataclass
from threading import BoundedSemaphore, Lock
from time import perf_counter

from app.chat_events import check_chat_cancelled
from app.config import get_settings


@dataclass(frozen=True)
class ChannelExecution[T]:
    status: str
    duration_ms: float
    value: T | None = None


class RetrievalChannelExecutor:
    def __init__(self, workers: int):
        self._pools = {
            name: ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"retrieval-{name}")
            for name in ("keyword", "embedding", "rerank")
        }
        self._slots = {name: BoundedSemaphore(workers) for name in self._pools}

    def run[T](self, tasks: dict[str, Callable[[], T]], timeout: float) -> dict[str, ChannelExecution[T]]:
        results: dict[str, ChannelExecution[T]] = {}
        pending: dict[Future, tuple[str, float]] = {}
        try:
            for name, task in tasks.items():
                check_chat_cancelled()
                slot = self._slots[name]
                if not slot.acquire(blocking=False):
                    results[name] = ChannelExecution("saturated", 0)
                    continue
                started = perf_counter()
                try:
                    future = self._pools[name].submit(copy_context().run, _execute, task, started)
                except Exception:
                    slot.release()
                    results[name] = ChannelExecution("error", 0)
                    continue
                future.add_done_callback(lambda _future, held_slot=slot: held_slot.release())
                pending[future] = (name, started)

            while pending:
                check_chat_cancelled()
                for future, (name, started) in list(pending.items()):
                    elapsed = perf_counter() - started
                    if future.done():
                        # BaseException (including ChatCancelled) must bypass fallback.
                        outcome = future.result()
                        results[name] = (outcome if outcome.duration_ms <= timeout * 1000
                                         else ChannelExecution("timeout", outcome.duration_ms))
                        del pending[future]
                    elif elapsed >= timeout:
                        future.cancel()
                        results[name] = ChannelExecution("timeout", round(elapsed * 1000, 3))
                        del pending[future]
                if pending:
                    remaining = min(timeout - (perf_counter() - started) for _, started in pending.values())
                    wait(pending, timeout=max(0, min(0.05, remaining)), return_when=FIRST_COMPLETED)
            return results
        finally:
            # Cancels queued work only. Running pure retrieval may finish later,
            # but its result can no longer mutate a response or emit SSE events.
            for future in pending:
                future.cancel()

    def shutdown(self, *, wait: bool = False) -> None:
        for pool in self._pools.values():
            pool.shutdown(wait=wait, cancel_futures=True)


def _execute[T](task: Callable[[], T], started: float) -> ChannelExecution[T]:
    check_chat_cancelled()
    try:
        value = task()
    except Exception:
        # Do not copy exception text, paths or provider credentials to chat traces.
        return ChannelExecution("error", round((perf_counter() - started) * 1000, 3))
    check_chat_cancelled()
    return ChannelExecution("ok", round((perf_counter() - started) * 1000, 3), value)


_executor: RetrievalChannelExecutor | None = None
_executor_lock = Lock()


def get_retrieval_executor() -> RetrievalChannelExecutor:
    # Capacity is deployment configuration; changing it requires a process restart.
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = RetrievalChannelExecutor(get_settings().hybrid_retrieval.channel_workers)
        return _executor
