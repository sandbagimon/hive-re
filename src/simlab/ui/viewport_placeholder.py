from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from simlab.models.actor import Actor
from simlab.models.scene import Scene


class ViewportPlaceholder(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        self.refresh(None, None)

    def refresh(self, scene: Scene | None, selected_actor: Actor | None) -> None:
        scene_name = scene.name if scene else "No Scene"
        actor_count = len(scene.actors) if scene else 0
        selected = selected_actor.name if selected_actor else "None"
        self.label.setText(
            f"Scene: {scene_name}\n"
            f"Actors: {actor_count}\n"
            f"Selected Actor: {selected}\n\n"
            "MuJoCo viewport will be implemented in the next milestone."
        )
