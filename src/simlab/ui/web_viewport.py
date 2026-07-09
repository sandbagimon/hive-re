from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.services.simulation_session import SimulationState


class ViewportBridge(QObject):
    """Qt WebChannel bridge for selection and transform updates from JavaScript."""

    viewport_ready = Signal()
    actor_selected = Signal(str)
    actor_transform_changed = Signal(str, object)

    @Slot()
    def viewportReady(self) -> None:
        self.viewport_ready.emit()

    @Slot(str)
    def selectActor(self, actor_id: str) -> None:
        self.actor_selected.emit(actor_id)

    @Slot(str, str)
    def updateActorTransform(self, actor_id: str, transform_json: str) -> None:
        self.actor_transform_changed.emit(actor_id, json.loads(transform_json))


class WebViewport(QWebEngineView):
    """three.js viewport hosted inside QtWebEngine."""

    actor_selected = Signal(str)
    actor_transform_changed = Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self._ready = False
        self._pending_scene: Scene | None = None
        self._pending_selected_actor_id: str | None = None

        self.bridge = ViewportBridge()
        self.bridge.viewport_ready.connect(self._mark_ready)
        self.bridge.actor_selected.connect(self.actor_selected)
        self.bridge.actor_transform_changed.connect(self.actor_transform_changed)

        self.channel = QWebChannel(self.page())
        self.channel.registerObject("simlabBridge", self.bridge)
        self.page().setWebChannel(self.channel)

        html_path = Path(__file__).resolve().parents[1] / "web_viewport" / "index.html"
        self.load(QUrl.fromLocalFile(str(html_path)))

    def refresh(self, scene: Scene | None, selected_actor: Actor | None) -> None:
        self._pending_scene = scene
        self._pending_selected_actor_id = selected_actor.id if selected_actor else None
        if self._ready:
            self._push_state()

    def _mark_ready(self) -> None:
        self._ready = True
        self._push_state()

    def _push_state(self) -> None:
        if self._pending_scene is None:
            return
        scene_json = json.dumps(self._pending_scene.to_dict())
        selected_actor_id = self._pending_selected_actor_id or ""
        self.page().runJavaScript(f"window.simlabViewport.setSceneFromJson({scene_json!r});")
        self.page().runJavaScript(f"window.simlabViewport.selectActor({selected_actor_id!r});")

    def apply_simulation_state(self, state: SimulationState) -> None:
        state_json = json.dumps(state.to_dict())
        self.page().runJavaScript(
            f"window.simlabViewport.setSimulationStateFromJson({state_json!r});"
        )

    def clear_simulation_state(self) -> None:
        self.page().runJavaScript("window.simlabViewport.clearSimulationState();")
