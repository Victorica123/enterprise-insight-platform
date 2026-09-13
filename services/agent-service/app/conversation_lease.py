"""Renew a turn while blocking provider calls run; fence lost leases at stages."""

from contextlib import contextmanager
from threading import Event, Thread

from app.chat_events import bind_chat_guard
from app.config import get_settings
from app.conversation_store import ConversationBusy, ConversationLease, renew_turn


@contextmanager
def keep_turn_alive(lease: ConversationLease | None):
    if lease is None:
        yield
        return
    stopped, lost = Event(), Event()
    renew_turn(lease)

    def renew():
        interval = get_settings().conversation_lease_seconds / 3
        while not stopped.wait(interval):
            try:
                renew_turn(lease)
            except Exception:
                lost.set()
                return

    def check():
        if lost.is_set():
            raise ConversationBusy("Conversation lease could not be renewed; retry this turn.")

    worker = Thread(target=renew, name="conversation-lease", daemon=True)
    worker.start()
    try:
        with bind_chat_guard(check):
            yield
    finally:
        stopped.set()
        worker.join(timeout=6)
