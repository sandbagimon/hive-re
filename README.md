# SimLab

SimLab is a simulation-first desktop robotics scene editor MVP. The initial goal is a clean local scaffold: scene authoring, JSON project files, MJCF export, and a headless MuJoCo runner. It has no cloud service, login flow, online marketplace, or third-party product branding.

## Architecture

```text
SimLab Desktop
+-- PySide6 UI
|   +-- Asset Browser
|   +-- Scene Tree
|   +-- Property Panel
|   +-- three.js Viewport
|   +-- Console
+-- Scene Model
|   +-- scene.json
+-- Export Layer
|   +-- MJCF exporter
+-- Simulation Layer
    +-- MuJoCo runner
```

## Installation

Run these commands from the repository root.

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

On macOS or Linux, activate the virtual environment with `source .venv/bin/activate`.

## Run

```bash
python -m simlab.app
```

The desktop app opens with an asset browser, scene tree, three.js viewport, property panel, and console. Primitive assets can be added to the scene and exported to `exports/scene.xml`.

The viewport is a local QtWebEngine view backed by vendored three.js files. It renders primitive actors, supports orbit camera controls, click selection, and a basic translate gizmo for moving selected actors.

## Tests

```bash
python -m pytest
```

The tests cover the scene model, project save/load behavior, scene service actor operations, and MJCF export. MuJoCo model loading is skipped automatically if MuJoCo is not installed.

## Current Limitations

- The viewport supports primitive editing only; it is not yet a MuJoCo-rendered live view.
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

## Third-Party Code

- three.js r160 is vendored under `src/simlab/web_viewport/vendor/` and distributed under the MIT License.
