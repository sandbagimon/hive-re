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
    +-- Project IO / OpenUSD Import / Validation / MJCF Export
    +-- MuJoCo Session + Joint Control / Trajectory / Recording
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

Use **Import USD** to add `.usd`, `.usda`, `.usdc`, or `.usdz` assets. The importer resolves stage transforms, converts stage units and Y-up coordinates to SimLab's meter/Z-up convention, merges visible `UsdGeomMesh` data into a project cache, and registers the result in the Asset Browser. Imported actors use the same Transform and Physics inspector as primitive actors.

OpenUSD physics values are imported when authored, including rigid-body state, mass/density, and basic friction. The generated project cache contains viewport geometry plus an OBJ collision mesh. Export and simulation convert that asset to a MuJoCo mesh geom, so the default runtime does not require MuJoCo's experimental native USD decoder.

OpenUSD articulations are imported as robot actors with independent links, colliders, inertial properties, revolute joints, and position drives. The Scene Tree and viewport preserve the robot hierarchy; joint targets, jog controls, and editable keyframe trajectories drive the generated MuJoCo articulation while live link poses and joint feedback remain separate from authoring transforms.

Robot trajectories can be saved in the scene, reopened, edited, and replayed. The Recording panel selects joints, joint-state sensors, and IMUs independently, then reports fixed physics rows separately from emitted sensor events. Session merges typed fixed-step events into deterministic JSON and CSV: joint-state sensors use 5 stable columns and IMUs use 13 link/vector columns. CSV leaves all sensor columns empty between real samples instead of duplicating stale latest values, and legacy joint-sensor artifacts remain readable.

The command bar provides 0.25x, 0.5x, 1x, and 2x simulation-speed controls plus measured real-time-factor feedback. Speed changes scale fixed-step scheduling without changing the authored MuJoCo timestep or trajectory/recording timestamps.

Python controllers can attach to a MuJoCo session through an immutable per-step observation/action API. Controller exceptions and deadline overruns are isolated as runtime faults without stopping physics; manual targets, trajectory playback, and Python controllers are explicit mutually exclusive control sources. See [`docs/CONTROLLER_API.md`](docs/CONTROLLER_API.md).

The robot Inspector Controller section explicitly loads trusted project-local Python files, supports reload and detach, and displays callback status, step count, and execution duration. Controller code is never executed by opening a scene.

`simlab.controllers.JointPositionPdController` provides a bounded qpos/qvel outer loop for MuJoCo position drives. A project-loadable two-joint example is available at [`examples/controllers/two_joint_pd.py`](examples/controllers/two_joint_pd.py).

The robotics schema includes fixed-clock `joint_state` sensors with stable IDs, qpos/qvel payloads, simulation timestamps, and monotonic sequence numbers. It also defines link-mounted IMUs with an explicit local sensor pose: orientation is `world_from_sensor` xyzw, while angular velocity and MuJoCo accelerometer output are expressed in the sensor frame. MJCF export attaches an IMU site to the referenced link and emits frame-quaternion, gyro, and accelerometer channels; the Session maps their addresses and publishes a typed fixed-step runtime sample. Sensor update rates are exact integer divisors of the physics rate and remain independent of UI refresh, pause gaps, and target real-time factor. Robot Tree selection opens a type-specific live Sensor Inspector; the real Qt workflow verifies joint-state and IMU sensors can coexist, pause, and reset without changing the authoring scene.

Primitive actors expose basic physics properties in the Property Panel: Dynamic, Mass, and Friction. Dynamic actors export with MuJoCo free joints, while static actors export as fixed world geoms.

Primitive geometry follows a shared viewport/MuJoCo contract: Box sizes are half extents, Sphere size is radius, Cylinder size is radius plus half-height, rotations are XYZ radians, and actor scale is baked into exported colliders. Non-uniformly scaled spheres export as Ellipsoids, while cylinders require matching X/Y radial scale. Export contains no implicit collision ground.

The Property Panel includes Default, Rubber, Wood, Metal, and Ice physics materials plus explicit-mass and material-density modes. Presets link density, friction, MuJoCo contact parameters, and viewport roughness/metalness. The viewport collider debug toggle (`C`) displays dynamic/static wireframes and center-of-mass markers.

Run, Step, and Export MJCF perform a physics preflight first. The preflight validates dynamic/static configuration, mass, friction, primitive or imported mesh geometry, asset paths, and then asks MuJoCo to compile the generated MJCF. Blocking errors are shown with actor and field context in the UI and are also written to the Console Panel.

## Tests

```bash
python -m pytest
npm run typecheck
npm run test:frontend
```

The tests cover the scene model, project save/load behavior, scene service actor operations, scene history, geometry contracts, OpenUSD import, MJCF export, material presets, in-process MuJoCo state sync, and visual/physics fidelity. MuJoCo-specific tests are skipped automatically if MuJoCo is not installed.

## Current Limitations

- OpenUSD articulation import currently supports the documented fixed/revolute/position-drive subset; advanced joints, sensors, animation, and arbitrary USD physics extensions are reported as unsupported.
- Imported collision currently uses the merged visual mesh. Dedicated collision prim selection, convex decomposition, complex `UsdPreviewSurface` materials, textures, and animation are not yet supported.
- The viewport supports primitive and imported mesh editing with live MuJoCo pose playback, but it is not a full MuJoCo-native renderer.
- Trajectory playback, fixed-step recording, and real-time-factor controls are available; recording decimation and streaming output are not yet supported.
- Viewport editing tools do not yet include snapping or advanced transform constraints.
- MJCF export supports primitive and imported OpenUSD mesh actors with basic static/dynamic physics properties.
- Plane collision is infinite by MuJoCo definition; the built-in finite Ground uses a thin Box.
- The gym-style environment is a stub for a later integration.

## Next Milestone

**Gate 1 — Robot Simulation Closure（P0 阻塞项）**

The authoritative implementation order and handoff instructions for Codex are in
[`docs/CODEX_EXECUTION_ROADMAP.md`](docs/CODEX_EXECUTION_ROADMAP.md). The current vertical
slice is external OpenUSD robot-arm import -> robotics intermediate model -> MJCF/MuJoCo runtime
-> joint-space arm control. The robot must be loaded through Import USD rather than built into the
application. Read that document before starting the next implementation
task; `PRODUCT_PLAN.md` remains the long-term scope document.

The external OpenUSD robot import, joint-control vertical slice, general controller callback API, and first joint-state sensor runtime/Inspector are complete. The next platform gap is deterministic sensor recording/export followed by IMU and contact/force sensing.

1. **Contact sensing**: Add contact/force schema, aggregation semantics, recording fields, and UI inspection.
2. **Sensor authoring**: Add Inspector controls for creating, editing, and deleting mounted sensors.
3. **Clock hardening**: Extend soak coverage for variable host load and long recording sessions.
4. **Authoring**: Add dedicated collision prim workflows and a consolidated validation panel.

See [`docs/PRODUCT_PLAN.md`](docs/PRODUCT_PLAN.md) for the complete milestone matrix and phased roadmap.

## Third-Party Code

- three.js r160 is vendored under `src/simlab/web_viewport/vendor/` and distributed under the MIT License.
- OpenUSD Python bindings are installed through the `usd-core` package. OpenUSD 26.05+ is distributed under the TOST license; see [third-party notices](docs/THIRD_PARTY_NOTICES.md).
