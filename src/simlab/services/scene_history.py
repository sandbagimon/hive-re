from __future__ import annotations

import copy
from typing import Any

from simlab.models.scene import Scene

SceneSnapshot = dict[str, Any]


class SceneHistory:
    """Snapshot-based undo/redo and dirty tracking for scene edits."""

    def __init__(self, scene: Scene, max_depth: int = 100) -> None:
        self.max_depth = max_depth
        self._undo_stack: list[SceneSnapshot] = []
        self._redo_stack: list[SceneSnapshot] = []
        self._saved_snapshot = self._snapshot(scene)

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def begin_change(self, scene: Scene) -> None:
        snapshot = self._snapshot(scene)
        if self._undo_stack and self._undo_stack[-1] == snapshot:
            return
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self.max_depth:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self, current_scene: Scene) -> Scene | None:
        if not self._undo_stack:
            return None
        self._redo_stack.append(self._snapshot(current_scene))
        return Scene.from_dict(self._undo_stack.pop())

    def redo(self, current_scene: Scene) -> Scene | None:
        if not self._redo_stack:
            return None
        self._undo_stack.append(self._snapshot(current_scene))
        return Scene.from_dict(self._redo_stack.pop())

    def reset(self, scene: Scene) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._saved_snapshot = self._snapshot(scene)

    def mark_saved(self, scene: Scene) -> None:
        self._saved_snapshot = self._snapshot(scene)

    def is_dirty(self, scene: Scene) -> bool:
        return self._snapshot(scene) != self._saved_snapshot

    def _snapshot(self, scene: Scene) -> SceneSnapshot:
        return copy.deepcopy(scene.to_dict())
