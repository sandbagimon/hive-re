from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from simlab.models.actor import Actor


class SceneTree(QWidget):
    actor_selected = Signal(str)
    actor_delete_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.list_widget = QListWidget()
        self.delete_button = QPushButton("Delete Selected")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.delete_button)

        self.list_widget.currentItemChanged.connect(self._current_changed)
        self.delete_button.clicked.connect(self._delete_current)

    def set_actors(self, actors: list[Actor], selected_actor_id: str | None = None) -> None:
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        selected_row = -1
        for row, actor in enumerate(actors):
            item = QListWidgetItem(actor.name)
            item.setData(Qt.ItemDataRole.UserRole, actor.id)
            self.list_widget.addItem(item)
            if actor.id == selected_actor_id:
                selected_row = row
        if selected_row >= 0:
            self.list_widget.setCurrentRow(selected_row)
        self.list_widget.blockSignals(False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self._delete_current()
            return
        super().keyPressEvent(event)

    def _current_changed(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        actor_id = current.data(Qt.ItemDataRole.UserRole)
        if actor_id:
            self.actor_selected.emit(str(actor_id))

    def _delete_current(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        actor_id = item.data(Qt.ItemDataRole.UserRole)
        if actor_id:
            self.actor_delete_requested.emit(str(actor_id))
