# SimLab Web Architecture

## Deployment boundary

SimLab has two independently buildable and deployable products:

```text
frontend/                         Python package
  src/ (TypeScript/three.js)       simlab-api (FastAPI)
  public/simlab-config.json   ->   /api/v1 projects/simulations/artifacts
  dist/ (static files)        <-   versioned WebSocket events
```

The frontend is static content and may be hosted by a CDN, object storage, Vite preview, nginx, or any other static server. The API never serves HTML, JavaScript, CSS, or three.js. The Python wheel does not package frontend files. Neither build requires the other process to be running.

The optional Qt application is only a web client. It loads `SIMLAB_FRONTEND_URL` (or `--frontend-url`) over HTTP(S); it does not register QWebChannel objects, start an API, receive a project filesystem root, or execute business logic.

## Runtime configuration

The frontend reads `simlab-config.json` relative to its deployed `index.html` with caching disabled:

```json
{
  "apiBaseUrl": "https://api.example.com",
  "webSocketBaseUrl": "wss://api.example.com",
  "apiVersion": "v1",
  "projectId": null,
  "accessToken": null
}
```

- `apiBaseUrl` and `webSocketBaseUrl` may point to a different host and deployment lifecycle.
- In Vite development mode both values are served as `same-origin`; Vite proxies `/api` and its WebSocket upgrade to the remote API. This lets Remote SSH/Dev Container users forward only port 5173. The production build still receives the explicit addresses from `frontend/public/simlab-config.json`.
- `projectId: null` creates a project for that client. A known opaque project ID reconnects to an existing in-memory project.
- `accessToken` is sent as an HTTP Bearer token and as the WebSocket `token` query parameter. Static configuration is visible to the browser; production identity should issue user-scoped tokens through a protected hosting layer and use HTTPS/WSS.
- Only `v1` is accepted. An incompatible frontend fails visibly instead of silently calling another API shape.

The checked-in config targets the loopback development API. A deployment can replace `frontend/dist/simlab-config.json` after `npm run build` without rebuilding JavaScript.

## HTTP resource contract

OpenAPI is published at `/api/v1/openapi.json`; interactive documentation is at `/api/docs`.

The v1 API uses explicit resources rather than method-name RPC:

- `projects`: create a project, update its canonical scene, list assets, import an OpenUSD upload bundle, run preflight, and create MJCF artifacts.
- `simulations`: create an isolated runtime for one project, control run/pause/step/reset/speed, targets, trajectories, recording, and an optional trusted controller.
- `artifacts`: opaque `art_...` references for imported cache data and downloadable MJCF/recording output.

IDs (`prj_...`, `sim_...`, `art_...`) cross the network. Absolute or project-relative server filesystem paths do not. Browser Open/Save and controller/OpenUSD input use upload content; output uses authenticated artifact downloads. The old `/api/rpc/{method}`, `/api/health`, and server path operations are not exposed by the backend.

Each simulation owns its own `WebApplication` and MuJoCo session. Updating one project stops only simulations belonging to that project. Creating a second browser client creates separate project and simulation IDs, so runtime state cannot overwrite another client.

## WebSocket recovery

Connect to:

```text
WS /api/v1/simulations/{simulation_id}/events?after_sequence=42&token=...
```

Every message includes `version`, `simulation_id`, monotonically increasing `sequence`, `type`, and `payload`. Types are `snapshot`, `state`, `status`, `console`, `title`, and `heartbeat`.

The initial connection receives a snapshot. On a short disconnection the client reconnects with its last sequence and the server replays only missing buffered events. If the cursor is absent or older than the bounded 512-event buffer, the server sends a fresh snapshot. Reconnection uses bounded exponential backoff and never changes simulation ID.

## Security boundary

- CORS uses an explicit origin allow-list. Development defaults include only loopback Vite ports 4173 and 5173; pass one or more `--cors-origin` values for deployment.
- Set `SIMLAB_API_TOKEN` or `--access-token` to require Bearer authentication for every project, simulation, and artifact HTTP route and the matching WebSocket token.
- An unauthenticated WebSocket is upgraded only to return the explicit application close code `4401`; clients can distinguish authorization failure from transport loss.
- Python controller execution is disabled by default. `--allow-controller-execution` is an explicit trusted-local opt-in; it is not a sandbox for untrusted code.
- Uploaded OpenUSD bundle names reject traversal and the application layer enforces its upload-size limit. Backend storage stays below the configured data root.
- Bind the API to loopback by default. Remote deployments should terminate TLS, issue scoped tokens, impose reverse-proxy request/rate quotas, and keep controller execution disabled unless the backend is dedicated to trusted code.

## Run independently

Backend:

```bash
simlab-api --host 127.0.0.1 --port 8765 \
  --data-root .simlab-data \
  --cors-origin http://127.0.0.1:4173 \
  --cors-origin http://127.0.0.1:5173
```

Frontend development server:

```bash
npm install
npm run dev:frontend
```

Production-like static preview:

```bash
npm run build
npm run preview:frontend
```

Optional Qt web client:

```bash
python -m pip install -e '.[desktop]'
SIMLAB_FRONTEND_URL=http://127.0.0.1:4173 simlab
```

## Verification

```bash
python -m pytest
python -m ruff check src tests
python -m mypy src
npm run typecheck
npm run test:frontend
npm run test:web
```

Playwright starts static frontend and API processes on different ports. Its acceptance suite covers ordinary editing/simulation/downloads, OpenUSD/controller/recording workflows, two-client resource isolation, and real WebSocket disconnect/replay with `after_sequence`.
