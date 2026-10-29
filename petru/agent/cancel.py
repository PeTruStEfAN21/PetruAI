"""Esc: one token per session that stops the model's reply and the commands of the turn in progress."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable


class Cancelled(KeyboardInterrupt):
    """The user stopped the turn. A KeyboardInterrupt, so every path that handles Ctrl+C handles it too."""


class CancelToken:
    """Set by the UI thread, checked by the agent thread; callbacks close what blocks (stream, process)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._callbacks: list[Callable[[], None]] = []

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            callbacks = list(self._callbacks)
        for fn in callbacks:
            with contextlib.suppress(Exception):  # a failed close must not keep Esc from stopping the rest
                fn()

    def reset(self) -> None:
        self._event.clear()

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled

    def on_cancel(self, fn: Callable[[], None]) -> Callable[[], None]:
        """Run `fn` on cancel (at once if already cancelled); returns the function that unregisters it."""
        with self._lock:
            late = self._event.is_set()
            if not late:
                self._callbacks.append(fn)
        if late:
            with contextlib.suppress(Exception):
                fn()

        def remove() -> None:
            with self._lock:
                if fn in self._callbacks:
                    self._callbacks.remove(fn)

        return remove
