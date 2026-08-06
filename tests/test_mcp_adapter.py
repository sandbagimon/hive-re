from __future__ import annotations

import json
from typing import Any

import anyio
import httpx
import pytest
from mcp import Client

from simlab.mcp.api_client import SimLabApiClient, SimLabApiError
from simlab.mcp.server import create_mcp_server, main


def test_mcp_exposes_structured_rest_resources_and_simulation_controls() -> None:
    requests: list[tuple[str, str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, body))
        assert request.headers.get("authorization") == "Bearer test-token"
        path = request.url.path
        if path == "/api/v1/health":
            return httpx.Response(200, json={"version": "v1", "status": "ok"})
        if path == "/api/v1/projects" and request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "version": "v1",
                    "id": "prj_1",
                    "name": body["name"],
                    "revision": 0,
                    "scene": {"name": "Empty", "actors": []},
                },
            )
        if path == "/api/v1/projects/prj_1":
            return httpx.Response(
                200,
                json={
                    "version": "v1",
                    "id": "prj_1",
                    "name": "MCP Project",
                    "revision": 1,
                    "scene": {"name": "Updated", "actors": []},
                },
            )
        if path == "/api/v1/projects/prj_1/scene":
            return httpx.Response(
                200,
                json={
                    "version": "v1",
                    "id": "prj_1",
                    "name": "MCP Project",
                    "revision": 1,
                    "scene": body,
                },
            )
        if path == "/api/v1/projects/prj_1/assets":
            return httpx.Response(
                200,
                json={"version": "v1", "assets": [{"id": "asset_box"}]},
            )
        if path == "/api/v1/projects/prj_1/preflight":
            return httpx.Response(
                200, json={"version": "v1", "ok": True, "issues": []}
            )
        if path == "/api/v1/simulations" and request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "version": "v1",
                    "id": "sim_1",
                    "project_id": body["project_id"],
                    "snapshot": {"status": "stopped", "sequence": 0},
                },
            )
        if path == "/api/v1/simulations/sim_1/snapshot":
            return httpx.Response(
                200,
                json={"version": "v1", "status": "running", "sequence": 2},
            )
        if path == "/api/v1/simulations/sim_1/joint-targets":
            return httpx.Response(200, json={"version": "v1", "targets": body["targets"]})
        if path == "/api/v1/simulations/sim_1/run":
            return httpx.Response(200, json={"version": "v1", "status": "running"})
        if path == "/api/v1/simulations/sim_1" and request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404, json={"detail": f"Unhandled test route: {path}"})

    async def exercise() -> None:
        api = SimLabApiClient(
            "http://simlab.test/api/v1/",
            access_token="test-token",
            transport=httpx.MockTransport(handler),
        )
        server = create_mcp_server(api)
        async with Client(server, raise_exceptions=True) as client:
            tools = await client.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert {
                "simlab_health",
                "simlab_update_scene",
                "simlab_preflight_project",
                "simlab_create_simulation",
                "simlab_set_joint_targets",
                "simlab_stop_simulation",
            } <= tool_names
            health_tool = next(tool for tool in tools.tools if tool.name == "simlab_health")
            stop_tool = next(
                tool for tool in tools.tools if tool.name == "simlab_stop_simulation"
            )
            assert health_tool.annotations is not None
            assert health_tool.annotations.read_only_hint is True
            assert stop_tool.annotations is not None
            assert stop_tool.annotations.destructive_hint is True

            health = await client.call_tool("simlab_health", {})
            assert health.structured_content == {"version": "v1", "status": "ok"}
            project = await client.call_tool(
                "simlab_create_project", {"name": "MCP Project"}
            )
            assert project.structured_content is not None
            assert project.structured_content["id"] == "prj_1"
            scene = {"name": "Updated", "actors": []}
            updated = await client.call_tool(
                "simlab_update_scene", {"project_id": "prj_1", "scene": scene}
            )
            assert updated.structured_content is not None
            assert updated.structured_content["scene"] == scene
            preflight = await client.call_tool(
                "simlab_preflight_project", {"project_id": "prj_1"}
            )
            assert preflight.structured_content is not None
            assert preflight.structured_content["ok"] is True
            simulation = await client.call_tool(
                "simlab_create_simulation", {"project_id": "prj_1"}
            )
            assert simulation.structured_content is not None
            assert simulation.structured_content["id"] == "sim_1"
            targets = await client.call_tool(
                "simlab_set_joint_targets",
                {"simulation_id": "sim_1", "targets": {"joint_arm": 0.5}},
            )
            assert targets.structured_content is not None
            assert targets.structured_content["targets"] == {"joint_arm": 0.5}
            running = await client.call_tool(
                "simlab_run_simulation", {"simulation_id": "sim_1"}
            )
            assert running.structured_content is not None
            assert running.structured_content["status"] == "running"
            stopped = await client.call_tool(
                "simlab_stop_simulation", {"simulation_id": "sim_1"}
            )
            assert stopped.structured_content == {"version": "v1", "status": "deleted"}

            resources = await client.list_resources()
            assert {str(resource.uri) for resource in resources.resources} == {
                "simlab://health"
            }
            templates = await client.list_resource_templates()
            assert len(templates.resource_templates) == 3
            health_resource = await client.read_resource("simlab://health")
            assert json.loads(health_resource.contents[0].text) == {
                "version": "v1",
                "status": "ok",
            }
            prompts = await client.list_prompts()
            assert [prompt.name for prompt in prompts.prompts] == ["simlab_review_project"]

    anyio.run(exercise)

    assert ("POST", "/api/v1/projects", {"name": "MCP Project"}) in requests
    assert (
        "PUT",
        "/api/v1/projects/prj_1/scene",
        {"name": "Updated", "actors": []},
    ) in requests
    assert (
        "PUT",
        "/api/v1/simulations/sim_1/joint-targets",
        {"targets": {"joint_arm": 0.5}},
    ) in requests


def test_mcp_api_client_reports_backend_errors() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "backend warming up"})

    async def exercise() -> None:
        api = SimLabApiClient(
            "http://simlab.test",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(SimLabApiError, match=r"503.*backend warming up"):
                await api.health()
        finally:
            await api.close()

    anyio.run(exercise)


def test_mcp_api_client_rejects_path_injection_before_http() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    async def exercise() -> None:
        api = SimLabApiClient(
            "http://simlab.test",
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(SimLabApiError, match="Invalid SimLab prj resource ID"):
                await api.get_project("../../health")
            with pytest.raises(SimLabApiError, match="Invalid SimLab simulation command"):
                await api.simulation_command("sim_1", "../projects")
        finally:
            await api.close()

    anyio.run(exercise)
    assert called is False


def test_mcp_refuses_an_unauthenticated_non_loopback_listener() -> None:
    with pytest.raises(SystemExit, match="refusing to expose MCP"):
        main(
            [
                "--transport",
                "streamable-http",
                "--host",
                "0.0.0.0",
            ]
        )
