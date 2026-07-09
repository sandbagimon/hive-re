from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from simlab.models.scene import Scene
from simlab.services.mjcf_exporter import export_scene_to_mjcf
from simlab.services.project_service import load_scene, save_scene
from simlab.services.scene_history import SceneHistory
from simlab.services.scene_service import SceneService
from simlab.services.simulation_service import SimulationService
from simlab.ui.asset_browser import AssetBrowser
from simlab.ui.console_panel import ConsolePanel
from simlab.ui.property_panel import PropertyPanel
from simlab.ui.scene_tree import SceneTree
from simlab.ui.web_viewport import WebViewport


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project_root = self._find_project_root()
        self.scene_service = SceneService(Scene())
        self.history = SceneHistory(self.scene_service.scene)
        self.current_path: Path | None = None
        self.selected_actor_id: str | None = None

        self.console = ConsolePanel()
        self.simulation_service = SimulationService(
            self.project_root,
            self.console.append_message,
        )
        self.simulation_timer = QTimer(self)
        self.simulation_timer.setInterval(16)
        self.asset_browser = AssetBrowser(self.project_root / "assets" / "metadata.json")
        self.scene_tree = SceneTree()
        self.property_panel = PropertyPanel()
        self.viewport = WebViewport()

        self.setWindowTitle("SimLab")
        self.resize(1200, 800)
        self._build_toolbar()
        self._build_layout()
        self._connect_signals()
        self.refresh_ui()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addAction("New Scene", self.new_scene)
        toolbar.addAction("Open", self.open_scene)
        toolbar.addAction("Save", self.save_current_scene)
        toolbar.addAction("Save As", self.save_scene_as)
        self.undo_action = toolbar.addAction("Undo", self.undo)
        self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.redo_action = toolbar.addAction("Redo", self.redo)
        self.redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        toolbar.addAction("Export MJCF", self.export_mjcf)
        toolbar.addAction("Run Simulation", self.run_simulation)
        toolbar.addAction("Pause Simulation", self.pause_simulation)
        toolbar.addAction("Step Simulation", self.step_simulation)
        toolbar.addAction("Reset Simulation", self.reset_simulation)

    def _build_layout(self) -> None:
        left = QSplitter()
        left.setOrientation(QtVertical)
        left.addWidget(self._panel("Asset Browser", self.asset_browser))
        left.addWidget(self._panel("Scene Tree", self.scene_tree))
        left.setSizes([360, 440])

        main_splitter = QSplitter()
        main_splitter.addWidget(left)
        main_splitter.addWidget(self._panel("Viewport", self.viewport))
        main_splitter.addWidget(self._panel("Properties", self.property_panel))
        main_splitter.setSizes([260, 680, 260])

        vertical = QSplitter()
        vertical.setOrientation(QtVertical)
        vertical.addWidget(main_splitter)
        vertical.addWidget(self._panel("Console", self.console))
        vertical.setSizes([620, 180])
        self.setCentralWidget(vertical)

    def _connect_signals(self) -> None:
        self.asset_browser.asset_activated.connect(self.add_asset)
        self.scene_tree.actor_selected.connect(self.select_actor)
        self.scene_tree.actor_delete_requested.connect(self.delete_actor)
        self.property_panel.actor_name_changed.connect(self.rename_actor)
        self.property_panel.actor_transform_changed.connect(self.update_transform)
        self.viewport.actor_selected.connect(self.select_actor)
        self.viewport.actor_transform_changed.connect(self.update_transform_from_viewport)
        self.simulation_timer.timeout.connect(self.advance_simulation)

    def new_scene(self) -> None:
        if not self._confirm_discard_changes():
            return
        self._clear_runtime_state()
        self.scene_service.new_scene()
        self.history.reset(self.scene_service.scene)
        self.current_path = None
        self.selected_actor_id = None
        self.console.append_message("Created a new scene.")
        self.refresh_ui()

    def open_scene(self) -> None:
        if not self._confirm_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Scene",
            str(self.project_root),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            self._clear_runtime_state()
            self.scene_service = SceneService(load_scene(path))
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))
            return
        self.current_path = Path(path)
        self.history.reset(self.scene_service.scene)
        self.selected_actor_id = None
        self.console.append_message(f"Opened scene: {path}")
        self.refresh_ui()

    def save_current_scene(self) -> bool:
        if self.current_path is None:
            return self.save_scene_as()
        try:
            save_scene(self.current_path, self.scene_service.scene)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return False
        self.history.mark_saved(self.scene_service.scene)
        self.console.append_message(f"Saved scene: {self.current_path}")
        self.refresh_ui()
        return True

    def save_scene_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Scene",
            str(self.project_root / "scene.json"),
            "JSON (*.json)",
        )
        if not path:
            return False
        self.current_path = Path(path)
        return self.save_current_scene()

    def export_mjcf(self) -> None:
        path = self.project_root / "exports" / "scene.xml"
        try:
            export_scene_to_mjcf(self.scene_service.scene, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return
        self.console.append_message(f"Exported MJCF: {path}")

    def run_simulation(self) -> None:
        try:
            state = self.simulation_service.start(self.scene_service.scene)
        except Exception as exc:
            QMessageBox.critical(self, "Simulation Failed", str(exc))
            return
        self.viewport.apply_simulation_state(state)
        self.simulation_timer.start()

    def pause_simulation(self) -> None:
        self.simulation_timer.stop()
        self.simulation_service.pause()

    def step_simulation(self) -> None:
        self.simulation_timer.stop()
        try:
            state = self.simulation_service.step_once(self.scene_service.scene)
        except Exception as exc:
            QMessageBox.critical(self, "Simulation Failed", str(exc))
            return
        self.viewport.apply_simulation_state(state)

    def reset_simulation(self) -> None:
        self.simulation_timer.stop()
        self.simulation_service.reset()
        self.viewport.clear_simulation_state()

    def advance_simulation(self) -> None:
        state = self.simulation_service.step_frame()
        if state is None:
            self.simulation_timer.stop()
            return
        self.viewport.apply_simulation_state(state)

    def add_asset(self, asset: dict[str, Any]) -> None:
        self._record_scene_change()
        properties = copy.deepcopy(asset.get("default_properties", {}))
        if "primitive" in asset:
            properties["primitive"] = asset["primitive"]
        actor = self.scene_service.add_actor(
            name=str(asset.get("name", "Actor")),
            actor_type="object",
            asset_id=str(asset.get("id", "")),
            properties=properties,
        )
        self.selected_actor_id = actor.id
        self.console.append_message(f"Added actor: {actor.name}")
        self.refresh_ui()

    def select_actor(self, actor_id: str) -> None:
        self.selected_actor_id = actor_id
        self.refresh_ui()

    def delete_actor(self, actor_id: str) -> None:
        actor = self.scene_service.get_actor(actor_id)
        if actor is None:
            return
        self._record_scene_change()
        self.scene_service.remove_actor(actor_id)
        if self.selected_actor_id == actor_id:
            self.selected_actor_id = None
        self.console.append_message(f"Deleted actor: {actor.name}")
        self.refresh_ui()

    def rename_actor(self, actor_id: str, name: str) -> None:
        actor = self.scene_service.get_actor(actor_id)
        next_name = name or "Actor"
        if actor is None or actor.name == next_name:
            return
        self._record_scene_change()
        self.scene_service.rename_actor(actor_id, name or "Actor")
        self.refresh_ui()

    def update_transform(self, actor_id: str, transform: object) -> None:
        actor = self.scene_service.get_actor(actor_id)
        if actor is None or actor.transform == transform:
            return
        self._record_scene_change()
        self.scene_service.update_transform(actor_id, transform)  # type: ignore[arg-type]
        self.refresh_ui()

    def update_transform_from_viewport(self, actor_id: str, transform_data: object) -> None:
        actor = self.scene_service.get_actor(actor_id)
        if actor is None or not isinstance(transform_data, dict):
            return
        next_position = self._vector_from_viewport(
            transform_data.get("position"),
            actor.transform.position,
        )
        next_rotation = self._vector_from_viewport(
            transform_data.get("rotation"),
            actor.transform.rotation,
        )
        next_scale = self._vector_from_viewport(
            transform_data.get("scale"),
            actor.transform.scale,
        )
        if (
            actor.transform.position == next_position
            and actor.transform.rotation == next_rotation
            and actor.transform.scale == next_scale
        ):
            return
        self._record_scene_change()
        actor.transform.position = next_position
        actor.transform.rotation = next_rotation
        actor.transform.scale = next_scale
        self.selected_actor_id = actor_id
        self.property_panel.set_actor(actor)
        self.scene_tree.set_actors(self.scene_service.list_actors(), self.selected_actor_id)
        self.viewport.refresh(self.scene_service.scene, actor)

    def undo(self) -> None:
        restored = self.history.undo(self.scene_service.scene)
        if restored is None:
            return
        self._clear_runtime_state()
        self.scene_service = SceneService(restored)
        self.console.append_message("Undo.")
        self.refresh_ui()

    def redo(self) -> None:
        restored = self.history.redo(self.scene_service.scene)
        if restored is None:
            return
        self._clear_runtime_state()
        self.scene_service = SceneService(restored)
        self.console.append_message("Redo.")
        self.refresh_ui()

    def is_dirty(self) -> bool:
        return self.history.is_dirty(self.scene_service.scene)

    def _vector_from_viewport(self, value: object, fallback: list[float]) -> list[float]:
        if not isinstance(value, list) or len(value) != 3:
            return list(fallback)
        return [float(item) for item in value]

    def refresh_ui(self) -> None:
        actors = self.scene_service.list_actors()
        if self.selected_actor_id and self.scene_service.get_actor(self.selected_actor_id) is None:
            self.selected_actor_id = None
        selected_actor = (
            self.scene_service.get_actor(self.selected_actor_id) if self.selected_actor_id else None
        )
        self.scene_tree.set_actors(actors, self.selected_actor_id)
        self.property_panel.set_actor(selected_actor)
        self.viewport.refresh(self.scene_service.scene, selected_actor)
        self._refresh_window_title()
        self._refresh_history_actions()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()

    def _record_scene_change(self) -> None:
        self._clear_runtime_state()
        self.history.begin_change(self.scene_service.scene)

    def _clear_runtime_state(self) -> None:
        self.simulation_timer.stop()
        if self.simulation_service.session is not None:
            self.simulation_service.reset()
        self.viewport.clear_simulation_state()

    def _confirm_discard_changes(self) -> bool:
        if not self.is_dirty():
            return True
        result = QMessageBox.warning(
            self,
            "Unsaved Changes",
            "The current scene has unsaved changes.",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if result == QMessageBox.StandardButton.Save:
            return self.save_current_scene()
        return result == QMessageBox.StandardButton.Discard

    def _refresh_window_title(self) -> None:
        dirty = "*" if self.is_dirty() else ""
        scene_name = self.scene_service.scene.name
        path = f" - {self.current_path}" if self.current_path else ""
        self.setWindowTitle(f"{dirty}SimLab - {scene_name}{path}")

    def _refresh_history_actions(self) -> None:
        self.undo_action.setEnabled(self.history.can_undo())
        self.redo_action.setEnabled(self.history.can_redo())

    def _panel(self, title: str, widget: QWidget) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        label = QLabel(title)
        layout.addWidget(label)
        layout.addWidget(widget)
        return panel

    def _find_project_root(self) -> Path:
        source_root = Path(__file__).resolve().parents[2]
        if (source_root / "assets" / "metadata.json").exists():
            return source_root
        return Path.cwd()


try:
    from PySide6.QtCore import Qt

    QtVertical = Qt.Orientation.Vertical
except Exception:  # pragma: no cover - import-time fallback for type checkers
    QtVertical = 2
