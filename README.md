# SimLab

SimLab is a simulation-first desktop robotics scene editor MVP. The initial goal is a clean local scaffold: scene authoring, JSON project files, MJCF export, and a headless MuJoCo runner. It has no cloud service, login flow, online marketplace, or third-party product branding.

## Architecture

```text
SimLab Desktop
+-- PySide6 UI
|   +-- Asset Browser
|   +-- Scene Tree
|   +-- Property Panel
|   +-- Viewport Placeholder
|   +-- Console
+-- Scene Model
|   +-- scene.json
+-- Export Layer
|   +-- MJCF exporter
+-- Simulation Layer
    +-- MuJoCo runner
```

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
```

On macOS or Linux, activate the virtual environment with `source .venv/bin/activate`.

## Run

```bash
python -m simlab.app
```

The desktop app opens with an asset browser, scene tree, placeholder viewport, property panel, and console. Primitive assets can be added to the scene and exported to `exports/scene.xml`.

## Tests

```bash
pytest
```

The tests cover the scene model, project save/load behavior, scene service actor operations, and MJCF export. MuJoCo model loading is skipped automatically if MuJoCo is not installed.

## Current Limitations

- The viewport is a placeholder; no live 3D rendering is implemented yet.
- The simulation runner is headless and runs a short fixed loop.
- MJCF export supports primitive box, sphere, and cylinder actors only.
- Rotation export is intentionally minimal in this milestone.
- The gym-style environment is a stub for a later integration.

## Next Milestone

- Add a MuJoCo-backed viewport.
- Expand actor types for robots, terrains, cameras, and lights.
- Add richer validation for scene files and asset metadata.
- Introduce timeline controls and simulation state inspection.
- Flesh out the environment API for training and evaluation workflows.
