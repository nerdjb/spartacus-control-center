"""Undo/redo for LCD Studio layouts.

Snapshot-based command history: every mutation pushes a full layout snapshot
(small JSON documents, capped stack), which makes arbitrary operations —
drag moves, grouping, QDT import, preset switches — uniformly undoable
without per-operation bookkeeping.
"""

from __future__ import annotations

import copy
from typing import Optional


class UndoStack:
    def __init__(self, limit: int = 100):
        if limit < 2:
            raise ValueError("limit must be >= 2")
        self.limit = limit
        self._undo: list[dict] = []
        self._redo: list[dict] = []

    # -- recording -----------------------------------------------------------

    def push(self, snapshot: dict) -> None:
        """Record *snapshot* as the state BEFORE an upcoming mutation."""
        self._undo.append(copy.deepcopy(snapshot))
        if len(self._undo) > self.limit:
            self._undo.pop(0)
        self._redo.clear()

    # -- traversal ---------------------------------------------------------------

    def undo(self, current: dict) -> Optional[dict]:
        """Roll *current* back; returns the restored snapshot or None."""
        if not self._undo:
            return None
        self._redo.append(copy.deepcopy(current))
        return self._undo.pop()

    def redo(self, current: dict) -> Optional[dict]:
        if not self._redo:
            return None
        self._undo.append(copy.deepcopy(current))
        return self._redo.pop()

    # -- status -----------------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
