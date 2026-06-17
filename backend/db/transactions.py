"""Conservative multi-collection write boundary helpers."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WriteCompensationScope:
    """Collect best-effort compensation callbacks for related writes."""

    name: str
    _callbacks: list[Callable[[], Any]] = field(default_factory=list)
    committed: bool = False

    def compensate_with(self, callback: Callable[[], Any]) -> None:
        if not self.committed:
            self._callbacks.append(callback)

    def commit(self) -> None:
        self.committed = True
        self._callbacks.clear()

    def rollback(self) -> None:
        for callback in reversed(self._callbacks):
            try:
                callback()
            except Exception:  # nosec B112
                continue
        self._callbacks.clear()


@contextmanager
def multi_collection_write(name: str):
    """Mark a multi-collection write and run compensations on exceptions."""

    scope = WriteCompensationScope(name=name)
    try:
        yield scope
    except Exception:
        scope.rollback()
        raise
    else:
        scope.commit()


__all__ = ["WriteCompensationScope", "multi_collection_write"]
