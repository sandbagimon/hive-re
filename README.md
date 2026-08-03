# SimLab

SimLab is a simulation-first robotics scene editor MVP. Its independently built TypeScript/three.js frontend runs in a standard browser and communicates with a separately deployed Python API over versioned HTTP resources and WebSocket events. An optional PySide6/QWebEngine program is only a web client for the same hosted frontend. Python provides OpenUSD import, MJCF export, validation, controllers, recording, sensors, and isolated MuJoCo simulation resources. It has no cloud service, login flow, online marketplace, or third-party product branding.

## Architecture

```text
SimLab frontend (static deployment)
+-- Browser or optional PySide6/QWebEngine Client
+-- TypeScript Editor (`frontend/src`)
|   +-- Editor Store + History
|   +-- Asset Browser / Scene Tree / Inspector / Console
|   +-- three.js Viewport
+-- runtime `simlab-config.json`
    |
    +-- `/api/v1` HTTP resources + per-simulation WebSocket
        |
SimLab backend (independent Python deployment)
+-- Project / Simulation / Artifact Resource Manager
+-- Transport-neutral Python Application Service
    +-- Project IO / OpenUSD Import / Validation / MJCF Export
    +-- MuJoCo Session + Joint Control / Trajectory / Recording
```

## Installation

Run these commands from the repository root.

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
npm install
npm run build
```

On macOS or Linux, activate the virtual environment with `source .venv/bin/activate`. Install `-r requirements.txt` instead when developing or running the complete Python/Qt test suite. Install `-e '.[desktop]'` when the optional Qt desktop host is needed.

## Run

Run the complete backend stack (FastAPI on `8765` and the independent MuJoCo gRPC algorithm
data plane on `50051`):

```bash
./start_backend.sh
```

In a separate terminal, run the frontend:

```bash
./start_frontend.sh
```

Then open `http://127.0.0.1:5173`. For a production-like build use `npm run build` followed by `npm run preview:frontend`, which serves `frontend/dist` at `http://127.0.0.1:4173`. Deployment-specific API and WebSocket addresses are read from `simlab-config.json`, so the static bundle does not need to share a host or release cycle with Python.

The backend launcher checks both ports, verifies the HTTP health endpoint, and shuts down both
services together on `Ctrl+C`. Override its defaults with `SIMLAB_BACKEND_HOST`,
`SIMLAB_BACKEND_PORT`, `SIMLAB_DATA_ROOT`, `SIMLAB_ALGORITHM_HOST`,
`SIMLAB_ALGORITHM_PORT`, `SIMLAB_ALGORITHM_ASSET_ROOT`, or `SIMLAB_ALGORITHM_WORKERS`.
Additional command-line arguments are passed to the FastAPI process, for example
`./start_backend.sh --allow-controller-execution` on a trusted development machine.

For an authenticated development backend, export the same API token in both terminals before
starting the services. `start_frontend.sh` forwards it only into Vite's no-store runtime config;
it is visible to that browser session and is therefore intended for trusted development only:

```bash
export SIMLAB_API_TOKEN='replace-with-a-development-token'
./start_backend.sh
# In the frontend terminal, export the same value (or SIMLAB_FRONTEND_ACCESS_TOKEN), then:
./start_frontend.sh
```

Production deployments must issue user-scoped credentials outside the static bundle rather than
embedding a shared secret in `frontend/public/simlab-config.json`.

The optional desktop adapter remains available after installing the `desktop` extra:

```bash
SIMLAB_FRONTEND_URL=http://127.0.0.1:4173 simlab
```

The Qt program only loads that HTTP(S) URL. It does not embed the frontend, expose QWebChannel, or start/own the backend.

The browser app opens a TypeScript editor with an asset browser, scene tree, three.js viewport, property inspector, and console. Primitive assets can be added to the scene, downloaded as MJCF, and simulated with Run/Pause/Step/Reset controls. Scene JSON is opened and saved through native browser file workflows; OpenUSD bundles and trusted controller files are uploaded to the backend, while MJCF and recording artifacts are downloaded by the browser. The primitive asset set includes dynamic shapes plus static physics playground assets such as Ground, Table, and Ramp.

The viewport is a browser WebGL view backed by vendored three.js files. It renders primitive actors, supports orbit camera controls, click selection, selection outline, translate/rotate/scale gizmos, frame selected, and front/right/top/isometric camera shortcuts. During simulation, MuJoCo body poses arrive over WebSocket and are applied without modifying the authoring transforms.

The TypeScript Editor Store owns scene authoring state, selection, dirty tracking, and undo/redo. Python receives canonical scene resources for validation, export, preflight, and simulation; browser and server filesystem paths never cross the public API.

See [`docs/MODULAR_DEVELOPMENT.md`](docs/MODULAR_DEVELOPMENT.md) for module boundaries, dependency rules, the target package layout, and the incremental modularization roadmap.

Use **Import USD** for a self-contained `.usd`, `.usda`, `.usdc`, `.usdz`, or safe ZIP package. Use **Import USD Folder** for a composed asset with sublayers, payloads, references, or textures; relative directory paths are preserved through multipart upload. The importer resolves stage transforms, converts stage units and Y-up coordinates to SimLab's meter/Z-up convention, triangulates meshes and native geometric primitives, expands PointInstancer instances at the default time, and registers a relocatable project cache. See [`docs/OPENUSD_IMPORT.md`](docs/OPENUSD_IMPORT.md) for the supported subset and package rules.

OpenUSD physics values are imported when authored, including rigid-body state, mass/density, and basic friction. Dedicated `PhysicsCollisionAPI` geometry is preferred; otherwise import emits a warning and falls back to the visual mesh. Display colors, a bound `UsdPreviewSurface` base color/opacity, UVs, and the first base-color texture are carried into the Three.js viewport. Robot visuals are cached as one content-addressed typed-array geometry bundle with precomputed normals and browser cache headers, while legacy per-mesh JSON remains readable. The generated project cache also contains OBJ collision meshes. Export and simulation convert that asset to MuJoCo mesh geoms, so the default runtime does not require MuJoCo's experimental native USD decoder.

OpenUSD articulations are imported as robot actors with independent links, colliders, inertial properties, revolute joints, and position drives. The Scene Tree and viewport preserve the robot hierarchy; joint targets, jog controls, and editable keyframe trajectories drive the generated MuJoCo articulation while live link poses and joint feedback remain separate from authoring transforms.

Robot trajectories can be saved in the scene, reopened, edited, and replayed. The Recording panel selects joints, joint-state sensors, and IMUs independently, then reports fixed physics rows separately from emitted sensor events. Session merges typed fixed-step events into deterministic JSON and CSV: joint-state sensors use 5 stable columns and IMUs use 13 link/vector columns. CSV leaves all sensor columns empty between real samples instead of duplicating stale latest values, and legacy joint-sensor artifacts remain readable.

The command bar provides 0.25x, 0.5x, 1x, and 2x simulation-speed controls plus measured real-time-factor feedback. Speed changes scale fixed-step scheduling without changing the authored MuJoCo timestep or trajectory/recording timestamps.

Python controllers can attach to a MuJoCo session through an immutable per-step observation/action API. Controller exceptions and deadline overruns are isolated as runtime faults without stopping physics; manual targets, trajectory playback, and Python controllers are explicit mutually exclusive control sources. See [`docs/CONTROLLER_API.md`](docs/CONTROLLER_API.md).

Quadrotors use named rotor actuators and an engine-neutral quadratic thrust profile. The bundled Pegasus Iris can be driven through Python Controller, REST/Bridge, Gymnasium, or the existing gRPC data plane. See [`docs/QUADROTOR_CONTROL.md`](docs/QUADROTOR_CONTROL.md).

Training algorithms use a separate Gymnasium data plane. `SimLabEnv` composes an engine-neutral backend contract, a robot adapter, and a task, and can switch between an in-process `MujocoBackend` and an atomic gRPC backend without changing task or algorithm code. Install `.[algorithm]` for local training or `.[algorithm,remote]` for gRPC. See [`docs/ALGORITHM_BACKEND_DECOUPLING.md`](docs/ALGORITHM_BACKEND_DECOUPLING.md).

The robot Inspector Controller section explicitly loads trusted project-local Python files, supports reload and detach, and displays callback status, step count, and execution duration. Controller code is never executed by opening a scene.

`simlab.controllers.JointPositionPdController` provides a bounded qpos/qvel outer loop for MuJoCo position drives. A project-loadable two-joint example is available at [`examples/controllers/two_joint_pd.py`](examples/controllers/two_joint_pd.py).

The robotics schema includes fixed-clock `joint_state` sensors, link-mounted IMUs, and collider/link-scoped contact sensors. Contact aggregation maps stable collider IDs to MuJoCo geoms, sums native contact wrenches, and publishes bounded world-frame points/normals, normal force/impulse, and tangent force with a normal directed from the scoped geometry toward the other geometry. Contact samples run inside the fixed-step simulation session, can be inspected live with their resolved link/collider scope, and can be selected for typed JSON/CSV recording alongside joint-state and IMU events. IMU orientation is `world_from_sensor` xyzw, while angular velocity and MuJoCo accelerometer output are expressed in the sensor frame. Optional per-channel bias and Gaussian white noise uses deterministic stable sensor/channel streams; Reset replays the same sequence, while sensors without noise preserve exact values. Sensor update rates are exact integer divisors of the physics rate and remain independent of UI refresh, pause gaps, and target real-time factor.

Primitive actors expose basic physics properties in the Property Panel: Dynamic, Mass, and Friction. Dynamic actors export with MuJoCo free joints, while static actors export as fixed world geoms.

Primitive geometry follows a shared viewport/MuJoCo contract: Box sizes are half extents, Sphere size is radius, Cylinder size is radius plus half-height, rotations are XYZ radians, and actor scale is baked into exported colliders. Non-uniformly scaled spheres export as Ellipsoids, while cylinders require matching X/Y radial scale. Export contains no implicit collision ground.

The Property Panel includes Default, Rubber, Wood, Metal, and Ice physics materials plus explicit-mass and material-density modes. Presets link density, friction, MuJoCo contact parameters, and viewport roughness/metalness. The viewport collider debug toggle (`C`) displays dynamic/static wireframes and center-of-mass markers.

Run, Step, and Export MJCF perform a physics preflight first. The preflight validates dynamic/static configuration, mass, friction, primitive or imported mesh geometry, asset paths, and then asks MuJoCo to compile the generated MJCF. Blocking errors are shown with actor and field context in the UI and are also written to the Console Panel.

## Tests

```bash
python -m pytest
npm run typecheck
npm run test:frontend
npm run test:web
```

`npm run test:web` starts frontend and backend on different ports and verifies the cross-origin HTTP/WebSocket workflow in headless Chromium, including multi-client isolation and reconnect replay. See [`docs/WEB_ARCHITECTURE.md`](docs/WEB_ARCHITECTURE.md) for the v1 resource contract, runtime configuration, security controls, and deployment boundary.

The tests cover the scene model, project save/load behavior, scene service actor operations, scene history, geometry contracts, OpenUSD import, MJCF export, material presets, in-process MuJoCo state sync, and visual/physics fidelity. MuJoCo-specific tests are skipped automatically if MuJoCo is not installed.

## Current Limitations

- OpenUSD articulation import currently supports the documented fixed/revolute/position-drive subset; advanced joints, sensors, animation, and arbitrary USD physics extensions are reported as unsupported.
- OpenUSD import supports dedicated collision prims, native geometric primitives, default-time PointInstancer expansion, and a basic `UsdPreviewSurface` color/texture path. Multiple material groups, complex shader graphs, convex decomposition, skeletal animation, and editable variants are not yet supported.
- The viewport supports primitive and imported mesh editing with live MuJoCo pose playback, but it is not a full MuJoCo-native renderer.
- Trajectory playback, fixed-step recording, and real-time-factor controls are available; recording decimation and streaming output are not yet supported.
- Viewport editing tools do not yet include snapping or advanced transform constraints.
- MJCF export supports primitive and imported OpenUSD mesh actors with basic static/dynamic physics properties.
- Plane collision is infinite by MuJoCo definition; the built-in finite Ground uses a thin Box.
- A single-process Gymnasium environment and gRPC remote sessions are available; vectorized/MJX execution and a production TLS endpoint are not yet implemented.

## Next Milestone

**Gate 1 — Robot Simulation Closure（P0 阻塞项）**

The authoritative implementation order and handoff instructions for Codex are in
[`docs/CODEX_EXECUTION_ROADMAP.md`](docs/CODEX_EXECUTION_ROADMAP.md). The current vertical
slice is external OpenUSD robot-arm import -> robotics intermediate model -> MJCF/MuJoCo runtime
-> joint-space arm control. The robot must be loaded through Import USD rather than built into the
application. Read that document before starting the next implementation
task; `PRODUCT_PLAN.md` remains the long-term scope document.

The external OpenUSD robot import, joint-control vertical slice, controller API, trajectory/recording workflow, joint-state/IMU/contact sensors, deterministic sensor noise runtime, and browser/backend decoupling are complete. The next focused gap is sensor authoring and noise inspection.

1. **Sensor Noise Inspector**: Display deterministic seed, channel bias/stddev, and units with runtime/recording Reset replay E2E.
2. **Sensor authoring**: Add Inspector controls for creating, editing, and deleting mounted sensors.
3. **Clock hardening**: Extend soak coverage for variable host load and long recording sessions.
4. **Authoring**: Add dedicated collision prim workflows and a consolidated validation panel.

See [`docs/PRODUCT_PLAN.md`](docs/PRODUCT_PLAN.md) for the complete milestone matrix and phased roadmap.

## Third-Party Code

- three.js r160 is vendored under `frontend/src/vendor/` and distributed under the MIT License.
- OpenUSD Python bindings are installed through the `usd-core` package. OpenUSD 26.05+ is distributed under the TOST license; see [third-party notices](docs/THIRD_PARTY_NOTICES.md).
