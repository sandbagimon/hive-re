# BeeFoundrySim MCP Integration

## Boundary

The MCP server is an optional adapter, not a new simulation backend:

```text
MCP client
    | stdio or Streamable HTTP
beefoundrysim-mcp (stateless protocol adapter)
    | HTTP Bearer token + /api/v1
beefoundrysim-api (project/simulation/artifact resources)
    | application services
MuJoCo / OpenUSD / asset cache
```

`beefoundrysim-mcp` imports neither `ResourceManager` nor the MuJoCo runtime. It only calls the same
versioned REST resources used by the browser, so MCP, frontend, API, and algorithm backend can be
built, restarted, and deployed independently. Project IDs and simulation IDs remain opaque; no
server filesystem path crosses the MCP boundary.

## Install and start

Install the optional official Python SDK:

```bash
.venv/bin/python -m pip install -e '.[mcp]'
```

Start the normal backend first:

```bash
./start_backend.sh
```

For a local MCP client, configure stdio with the repository launcher. A client-neutral example is:

```json
{
  "mcpServers": {
    "beefoundrysim": {
      "command": "/home/simon/Desktop/hive-re/hive-re/start_mcp.sh",
      "env": {
        "BEEFOUNDRYSIM_API_URL": "http://127.0.0.1:8765"
      }
    }
  }
}
```

If the API uses authentication, add `BEEFOUNDRYSIM_API_TOKEN` to the MCP process environment. Do not put
the token in tool arguments: the adapter injects it as `Authorization: Bearer ...` for every REST
request.

For a Remote SSH or server workflow, run Streamable HTTP on the server loopback interface:

```bash
./start_mcp.sh --transport streamable-http --host 127.0.0.1 --port 8766
```

Forward port `8766` with VS Code or SSH and connect the local MCP client to
`http://127.0.0.1:8766/mcp`. SSE is intentionally not exposed because Streamable HTTP supersedes
it. A non-loopback bind is rejected unless `--allow-remote` is explicit; that mode has no MCP-layer
login and must sit behind an authenticated TLS reverse proxy. The REST token protects MCP-to-API
traffic, not the public MCP endpoint itself.

Configuration variables:

| Variable | Default | Meaning |
|---|---:|---|
| `BEEFOUNDRYSIM_API_URL` | `http://127.0.0.1:8765` | API origin or full `/api/v1` root |
| `BEEFOUNDRYSIM_API_TOKEN` | unset | REST Bearer token; never returned to MCP clients |
| `BEEFOUNDRYSIM_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |
| `BEEFOUNDRYSIM_MCP_HOST` | `127.0.0.1` | Streamable HTTP bind host |
| `BEEFOUNDRYSIM_MCP_PORT` | `8766` | Streamable HTTP port |
| `BEEFOUNDRYSIM_MCP_PATH` | `/mcp` | Streamable HTTP endpoint path |
| `BEEFOUNDRYSIM_MCP_API_TIMEOUT` | `30` | REST request timeout in seconds |

## Tools

Every tool returns structured JSON. Read and mutation/destructive hints are declared for clients
that support confirmation policies.

| Area | Tools |
|---|---|
| Backend | `beefoundrysim_health` |
| Project | `beefoundrysim_create_project`, `beefoundrysim_get_project`, `beefoundrysim_update_scene`, `beefoundrysim_list_assets` |
| Validation/export | `beefoundrysim_preflight_project`, `beefoundrysim_export_mjcf` |
| Simulation lifecycle | `beefoundrysim_create_simulation`, `beefoundrysim_get_simulation_snapshot`, `beefoundrysim_run_simulation`, `beefoundrysim_pause_simulation`, `beefoundrysim_step_simulation`, `beefoundrysim_reset_simulation`, `beefoundrysim_stop_simulation` |
| Runtime control | `beefoundrysim_set_simulation_speed`, `beefoundrysim_set_joint_targets`, `beefoundrysim_set_actuator_controls` |

`beefoundrysim_stop_simulation` deletes only the named simulation resource and is annotated destructive.
Scene replacement and target/control maps are idempotent. Creating projects, simulations, or export
artifacts is non-idempotent.

Recommended lifecycle:

1. Call `beefoundrysim_health`.
2. Create a project or obtain its opaque ID from the user/front end.
3. Inspect the project and assets, then call `beefoundrysim_preflight_project`.
4. Fix blocking issues before export or simulation creation.
5. Create a simulation, control it with its opaque simulation ID, and read snapshots.
6. Pause or delete the simulation explicitly when finished.

## Resources and prompt

- `beefoundrysim://health`
- `beefoundrysim://projects/{project_id}`
- `beefoundrysim://projects/{project_id}/assets`
- `beefoundrysim://simulations/{simulation_id}/snapshot`
- prompt `beefoundrysim_review_project(project_id)` for a read-only project/readiness review

The parameterized resources mirror existing GET endpoints; they do not introduce another source of
truth. High-frequency runtime events remain on the existing per-simulation WebSocket/gRPC data
planes rather than being polled through MCP.

## Current scope

The adapter deliberately omits arbitrary server paths, controller-source execution, large OpenUSD
uploads, binary artifact downloads, and high-frequency step loops. Those operations either need
file/blob negotiation, stronger user confirmation, or the existing browser/gRPC data plane. The
next MCP increment should add explicit artifact references and upload resources without accepting
unrestricted filesystem paths.
