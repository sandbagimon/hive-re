from __future__ import annotations

import sys

from simlab.main_window import MainWindow


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
