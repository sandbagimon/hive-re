from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget


class ConsolePanel(QWidget):
    message_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.output)
        self.message_received.connect(self.append_message)

    def append_message(self, message: str) -> None:
        self.output.append(message)

    def append_from_thread(self, message: str) -> None:
        self.message_received.emit(message)
