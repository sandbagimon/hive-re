from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget


class AssetBrowser(QWidget):
    asset_activated = Signal(dict)

    def __init__(self, metadata_path: Path) -> None:
        super().__init__()
        self.metadata_path = metadata_path
        self.list_widget = QListWidget()
        self.add_button = QPushButton("Add Selected Asset")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.add_button)

        self.list_widget.itemDoubleClicked.connect(self._activate_item)
        self.add_button.clicked.connect(self._activate_current)
        self.load_assets()

    def load_assets(self) -> None:
        self.list_widget.clear()
        metadata = self._read_metadata()
        for asset in metadata.get("assets", []):
            item = QListWidgetItem(str(asset.get("name", asset.get("id", "Asset"))))
            item.setData(Qt.ItemDataRole.UserRole, asset)
            self.list_widget.addItem(item)

    def _read_metadata(self) -> dict[str, Any]:
        if not self.metadata_path.exists():
            return {"assets": []}
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))

    def _activate_current(self) -> None:
        item = self.list_widget.currentItem()
        if item is not None:
            self._activate_item(item)

    def _activate_item(self, item: QListWidgetItem) -> None:
        asset = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(asset, dict):
            self.asset_activated.emit(asset)
