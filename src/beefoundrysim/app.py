from __future__ import annotations

import argparse
import sys

from beefoundrysim.main_window import MainWindow


def main() -> int:
    from PySide6.QtWidgets import QApplication

    parser = argparse.ArgumentParser(description="Open the BeeFoundrySim web frontend in Qt")
    parser.add_argument(
        "--frontend-url",
        help="independently served frontend URL (default: BEEFOUNDRYSIM_FRONTEND_URL or localhost:4173)",
    )
    args, qt_args = parser.parse_known_args()
    app = QApplication([sys.argv[0], *qt_args])
    window = MainWindow(frontend_url=args.frontend_url)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
