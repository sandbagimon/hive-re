from __future__ import annotations

import argparse
import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from simlab.mcp.api_client import SimLabApiClient

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
MUTATING = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
IDEMPOTENT_WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)


def create_mcp_server(api: SimLabApiClient) -> MCPServer:
    """Create an MCP server backed exclusively by the versioned SimLab REST API."""

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await api.close()

    server = MCPServer(
        "simlab",
        title="SimLab Robotics Simulation",
        version="0.1.0",
        instructions=(
            "Inspect a project and run simlab_preflight_project before exporting or "
            "starting a simulation. Treat project IDs, simulation IDs, actor IDs, joint "
            "IDs, and actuator IDs as opaque stable identifiers."
        ),
        lifespan=lifespan,
    )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def simlab_health() -> dict[str, Any]:
        """Check whether the configured SimLab REST backend is reachable."""
        return await api.health()

    @server.tool(annotations=MUTATING, structured_output=True)
    async def simlab_create_project(name: str = "Untitled Project") -> dict[str, Any]:
        """Create an isolated SimLab project and return its opaque project ID."""
        return await api.create_project(name)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def simlab_get_project(project_id: str) -> dict[str, Any]:
        """Read a project's canonical scene, name, and revision."""
        return await api.get_project(project_id)

    @server.tool(annotations=IDEMPOTENT_WRITE, structured_output=True)
    async def simlab_update_scene(
        project_id: str, scene: dict[str, Any]
    ) -> dict[str, Any]:
        """Replace a project's canonical authoring scene with a complete scene object."""
        return await api.update_scene(project_id, scene)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def simlab_list_assets(project_id: str) -> dict[str, Any]:
        """List assets available inside one SimLab project's asset catalog."""
        return await api.list_assets(project_id)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def simlab_preflight_project(project_id: str) -> dict[str, Any]:
        """Validate physics and ask MuJoCo to compile the generated model without running it."""
        return await api.preflight(project_id)

    @server.tool(annotations=MUTATING, structured_output=True)
    async def simlab_export_mjcf(project_id: str) -> dict[str, Any]:
        """Create an MJCF artifact after project preflight and return its download metadata."""
        return await api.export_mjcf(project_id)

    @server.tool(annotations=MUTATING, structured_output=True)
    async def simlab_create_simulation(project_id: str) -> dict[str, Any]:
        """Create a simulation resource from the project's current immutable scene snapshot."""
        return await api.create_simulation(project_id)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def simlab_get_simulation_snapshot(simulation_id: str) -> dict[str, Any]:
        """Read the current state, status, sensors, and sequence of a simulation."""
        return await api.simulation_snapshot(simulation_id)

    @server.tool(annotations=MUTATING, structured_output=True)
    async def simlab_run_simulation(simulation_id: str) -> dict[str, Any]:
        """Start or resume continuous physics stepping for a simulation resource."""
        return await api.simulation_command(simulation_id, "run")

    @server.tool(annotations=IDEMPOTENT_WRITE, structured_output=True)
    async def simlab_pause_simulation(simulation_id: str) -> dict[str, Any]:
        """Pause continuous physics stepping without deleting runtime state."""
        return await api.simulation_command(simulation_id, "pause")

    @server.tool(annotations=MUTATING, structured_output=True)
    async def simlab_step_simulation(simulation_id: str) -> dict[str, Any]:
        """Advance a paused simulation by one fixed physics step."""
        return await api.simulation_command(simulation_id, "step")

    @server.tool(annotations=IDEMPOTENT_WRITE, structured_output=True)
    async def simlab_reset_simulation(simulation_id: str) -> dict[str, Any]:
        """Reset a simulation to its initial state and deterministic sensor sequence."""
        return await api.simulation_command(simulation_id, "reset")

    @server.tool(annotations=DESTRUCTIVE, structured_output=True)
    async def simlab_stop_simulation(simulation_id: str) -> dict[str, Any]:
        """Stop and permanently delete a simulation resource."""
        return await api.stop_simulation(simulation_id)

    @server.tool(annotations=IDEMPOTENT_WRITE, structured_output=True)
    async def simlab_set_simulation_speed(
        simulation_id: str, factor: float
    ) -> dict[str, Any]:
        """Set the runtime pacing factor without changing the fixed physics timestep."""
        return await api.set_simulation_speed(simulation_id, factor)

    @server.tool(annotations=IDEMPOTENT_WRITE, structured_output=True)
    async def simlab_set_joint_targets(
        simulation_id: str, targets: dict[str, float]
    ) -> dict[str, Any]:
        """Atomically set stable joint-ID to position-target values in radians."""
        return await api.set_joint_targets(simulation_id, targets)

    @server.tool(annotations=IDEMPOTENT_WRITE, structured_output=True)
    async def simlab_set_actuator_controls(
        simulation_id: str, controls: dict[str, float]
    ) -> dict[str, Any]:
        """Atomically set stable actuator-ID to normalized/native control values."""
        return await api.set_actuator_controls(simulation_id, controls)

    @server.resource(
        "simlab://health",
        name="simlab-health",
        description="Current SimLab API health status.",
        mime_type="application/json",
    )
    async def health_resource() -> dict[str, Any]:
        return await api.health()

    @server.resource(
        "simlab://projects/{project_id}",
        name="simlab-project",
        description="Canonical SimLab project scene and revision.",
        mime_type="application/json",
    )
    async def project_resource(project_id: str) -> dict[str, Any]:
        return await api.get_project(project_id)

    @server.resource(
        "simlab://projects/{project_id}/assets",
        name="simlab-project-assets",
        description="Project-scoped SimLab asset catalog.",
        mime_type="application/json",
    )
    async def assets_resource(project_id: str) -> dict[str, Any]:
        return await api.list_assets(project_id)

    @server.resource(
        "simlab://simulations/{simulation_id}/snapshot",
        name="simlab-simulation-snapshot",
        description="Current SimLab simulation snapshot.",
        mime_type="application/json",
    )
    async def simulation_resource(simulation_id: str) -> dict[str, Any]:
        return await api.simulation_snapshot(simulation_id)

    @server.prompt()
    def simlab_review_project(project_id: str) -> str:
        """Build a safe project inspection and simulation-readiness workflow."""
        return (
            f"Review SimLab project {project_id}. Read simlab://projects/{project_id}, "
            f"read simlab://projects/{project_id}/assets, then call "
            f"simlab_preflight_project with project_id={project_id}. Summarize blocking "
            "physics issues, warnings, asset coverage, and the smallest safe fixes. Do not "
            "update the scene, export, or start a simulation unless the user explicitly asks."
        )

    return server


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Expose the SimLab REST API through Model Context Protocol."
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("SIMLAB_API_URL", "http://127.0.0.1:8765"),
        help="SimLab API origin or /api/v1 URL (default: %(default)s)",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.environ.get("SIMLAB_MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument(
        "--host", default=os.environ.get("SIMLAB_MCP_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("SIMLAB_MCP_PORT", "8766"))
    )
    parser.add_argument(
        "--path", default=os.environ.get("SIMLAB_MCP_PATH", "/mcp")
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help=(
            "allow an unauthenticated MCP listener on a non-loopback host; "
            "put it behind an authenticated TLS reverse proxy"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("SIMLAB_MCP_API_TIMEOUT", "30")),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    if args.port < 1 or args.port > 65535:
        raise SystemExit("--port must be between 1 and 65535")
    if not args.path.startswith("/"):
        raise SystemExit("--path must start with /")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than zero")
    if (
        args.transport == "streamable-http"
        and args.host not in {"127.0.0.1", "localhost", "::1"}
        and not args.allow_remote
    ):
        raise SystemExit(
            "refusing to expose MCP without authentication on a non-loopback host; "
            "use port forwarding or pass --allow-remote behind an authenticated TLS proxy"
        )
    api = SimLabApiClient(
        args.api_url,
        access_token=os.environ.get("SIMLAB_API_TOKEN"),
        timeout=args.timeout,
    )
    server = create_mcp_server(api)
    try:
        if args.transport == "stdio":
            server.run()
            return
        server.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            streamable_http_path=args.path,
            json_response=True,
            stateless_http=True,
        )
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
