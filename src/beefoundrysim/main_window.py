from __future__ import annotations

import os

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

DEFAULT_FRONTEND_URL = "http://127.0.0.1:4173"


class MainWindow(QMainWindow):
    """Optional desktop shell for the independently deployed web frontend."""

    def __init__(
        self,
        frontend_url: str | None = None,
    ) -> None:
        super().__init__()
        url = frontend_url or os.environ.get("BEEFOUNDRYSIM_FRONTEND_URL", DEFAULT_FRONTEND_URL)
        parsed = QUrl(url)
        if not parsed.isValid() or parsed.scheme() not in {"http", "https"}:
            raise ValueError("BEEFOUNDRYSIM_FRONTEND_URL must be an HTTP(S) URL")

        self.frontend_url = url
        self.web_view = QWebEngineView(self)
        self.web_view.load(parsed)
        self.setCentralWidget(self.web_view)
        self.setWindowTitle("BeeFoundrySim")
        self.resize(1360, 860)
