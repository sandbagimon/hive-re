"""Shared pytest configuration for BeeFoundrySim backend tests.

Ensures Qt applications can run in headless environments (CI, containers) by
defaulting to the offscreen platform plugin before any PySide6 QApplication is
created.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
