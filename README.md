# SimLab

SimLab is a simulation-first desktop robotics scene editor MVP. The editor UI is implemented in TypeScript and three.js, hosted by a thin PySide6/QWebEngine desktop shell. Python provides local project IO, MJCF export, validation, and MuJoCo simulation through a typed JSON RPC bridge. It has no cloud service, login flow, online marketplace, or third-party product branding.

## Architecture

```text
SimLab Desktop
+-- PySide6/QWebEngine Host
|   +-- Python JSON RPC Bridge
+-- TypeScript Editor
|   +-- Editor Store + History
|   +-- Asset Browser / Scene Tree / Inspector / Console
|   +-- three.js Viewport
+-- Python Services
    +-- Project IO / Validation / MJCF Export
    +-- MuJoCo Session + Live Pose Events
```

## Installation

Run these commands from the repository root.

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
npm install
npm run build
```

On macOS or Linux, activate the virtual environment with `source .venv/bin/activate`.

## Run

```bash
python -m simlab.app
```

The desktop app opens a TypeScript editor with an asset browser, scene tree, three.js viewport, property inspector, and console. Primitive assets can be added to the scene, exported to `exports/scene.xml`, and simulated with Run/Pause/Step/Reset controls. The primitive asset set includes dynamic shapes plus static physics playground assets such as Ground, Table, and Ramp.

The viewport is a local QtWebEngine view backed by vendored three.js files. It renders primitive actors, supports orbit camera controls, click selection, selection outline, translate/rotate/scale gizmos, frame selected, and front/right/top/isometric camera shortcuts. During simulation, MuJoCo body poses are pushed back into the viewport without modifying the authoring transforms.

The TypeScript Editor Store owns scene authoring state, selection, dirty tracking, and undo/redo. Python receives immutable scene snapshots only for Save, Export, Preflight, and Simulation RPC operations.

Primitive actors expose basic physics properties in the Property Panel: Dynamic, Mass, and Friction. Dynamic actors export with MuJoCo free joints, while static actors export as fixed world geoms.

Primitive geometry follows a shared viewport/MuJoCo contract: Box sizes are half extents, Sphere size is radius, Cylinder size is radius plus half-height, rotations are XYZ radians, and actor scale is baked into exported colliders. Non-uniformly scaled spheres export as Ellipsoids, while cylinders require matching X/Y radial scale. Export contains no implicit collision ground.

The Property Panel includes Default, Rubber, Wood, Metal, and Ice physics materials plus explicit-mass and material-density modes. Presets link density, friction, MuJoCo contact parameters, and viewport roughness/metalness. The viewport collider debug toggle (`C`) displays dynamic/static wireframes and center-of-mass markers.

Run, Step, and Export MJCF perform a physics preflight first. The preflight validates dynamic/static configuration, mass, friction, supported primitive geometry, and then asks MuJoCo to compile the generated MJCF. Blocking errors are shown with actor and field context in the UI and are also written to the Console Panel.

## Tests

```bash
python -m pytest
npm run typecheck
npm run test:frontend
```

The tests cover the scene model, project save/load behavior, scene service actor operations, scene history, geometry contracts, MJCF export, material presets, in-process MuJoCo state sync, and visual/physics fidelity. MuJoCo-specific tests are skipped automatically if MuJoCo is not installed.

## Current Limitations

- The viewport supports primitive editing and live MuJoCo pose playback, but it is not a full MuJoCo-native renderer.
- The simulation controls are minimal and do not yet include timeline playback, recording, or speed controls.
- Viewport editing tools are still primitive-only and do not yet include snapping or advanced transform constraints.
- MJCF export supports primitive box, sphere, cylinder, and plane actors with basic static/dynamic physics properties.
- Plane collision is infinite by MuJoCo definition; the built-in finite Ground uses a thin Box.
- The gym-style environment is a stub for a later integration.

## Next Milestone

- Add a MuJoCo-backed viewport.
- Expand actor types for robots, terrains, cameras, and lights.
- Add richer validation for scene files and asset metadata.
- Introduce timeline controls and simulation state inspection.
- Flesh out the environment API for training and evaluation workflows.

## Third-Party Code

- three.js r160 is vendored under `src/simlab/web_viewport/vendor/` and distributed under the MIT License.
