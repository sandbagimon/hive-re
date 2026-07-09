# SimLab

SimLab is a simulation-first desktop robotics scene editor MVP. The initial goal is a clean local scaffold: scene authoring, JSON project files, MJCF export, and local MuJoCo simulation state sync. It has no cloud service, login flow, online marketplace, or third-party product branding.

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
    +-- MuJoCo session
    +-- live body pose sync
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

The desktop app opens with an asset browser, scene tree, three.js viewport, property panel, and console. Primitive assets can be added to the scene, exported to `exports/scene.xml`, and simulated with Run/Pause/Step/Reset controls.

The viewport is a local QtWebEngine view backed by vendored three.js files. It renders primitive actors, supports orbit camera controls, click selection, selection outline, translate/rotate/scale gizmos, frame selected, and front/right/top/isometric camera shortcuts. During simulation, MuJoCo body poses are pushed back into the viewport without modifying the authoring transforms.

Scene edits are protected by dirty-state tracking and undo/redo. Unsaved scenes are marked in the window title, New/Open/Close prompt before discarding changes, and `Ctrl+Z` / `Ctrl+Shift+Z` undo or redo scene edits.

## Tests

```bash
python -m pytest
```

The tests cover the scene model, project save/load behavior, scene service actor operations, scene history, MJCF export, and in-process MuJoCo state sync. MuJoCo-specific tests are skipped automatically if MuJoCo is not installed.

## Current Limitations

- The viewport supports primitive editing and live MuJoCo pose playback, but it is not a full MuJoCo-native renderer.
- The simulation controls are minimal and do not yet include timeline playback, recording, or speed controls.
- Viewport editing tools are still primitive-only and do not yet include snapping or advanced transform constraints.
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
