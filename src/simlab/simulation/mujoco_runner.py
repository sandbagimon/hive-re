from __future__ import annotations

import sys
import time
from pathlib import Path


def run(xml_path: str | Path, steps: int = 100) -> int:
    """Run a short headless MuJoCo simulation."""
    try:
        import mujoco
    except ImportError:
        print("MuJoCo is not installed. Install the 'mujoco' package to run simulations.")
        return 2

    xml_file = Path(xml_path)
    if not xml_file.exists():
        print(f"MJCF file not found: {xml_file}")
        return 1

    try:
        model = mujoco.MjModel.from_xml_path(str(xml_file))
    except Exception as exc:
        print(f"Failed to load MJCF: {exc}")
        return 1

    data = mujoco.MjData(model)
    print(f"Loaded MJCF model from {xml_file}")
    for step in range(steps):
        mujoco.mj_step(model, data)
        if step % 10 == 0:
            print(f"step={step} time={data.time:.3f}")
        time.sleep(0.001)
    print("Simulation complete.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("Usage: python -m simlab.simulation.mujoco_runner exports/scene.xml")
        return 1
    return run(argv[0])


if __name__ == "__main__":
    raise SystemExit(main())
