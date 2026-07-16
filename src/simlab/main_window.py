from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QCloseEvent
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from simlab.editor_bridge import EditorBridge


class MainWindow(QMainWindow):
    """Thin desktop host for the TypeScript editor and Python RPC bridge."""

    def __init__(self, project_root: Path | None = None) -> None:
        super().__init__()
        self.project_root = project_root or self._find_project_root()
        self.web_view = QWebEngineView(self)
        self.bridge = EditorBridge(self, self.project_root)
        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject("simlabBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        self.bridge.titleChanged.connect(self.setWindowTitle)

        editor_path = Path(__file__).resolve().parent / "web_viewport" / "index.html"
        self.web_view.load(QUrl.fromLocalFile(str(editor_path)))
        self.setCentralWidget(self.web_view)
        self.setWindowTitle("SimLab - Untitled Scene")
        self.resize(1360, 860)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.bridge.confirm_close():
            self.bridge.shutdown()
            event.accept()
        else:
            event.ignore()

    @staticmethod
    def _find_project_root() -> Path:
        source_root = Path(__file__).resolve().parents[2]
        if (source_root / "assets" / "metadata.json").exists():
            return source_root
        return Path.cwd()
