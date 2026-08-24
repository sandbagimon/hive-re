from __future__ import annotations

import re
from typing import Any

import httpx


class BeeFoundrySimApiError(RuntimeError):
    """A transport or application error returned by the BeeFoundrySim REST API."""


class BeeFoundrySimApiClient:
    """Small async client that keeps the MCP adapter behind the public REST boundary."""

    def __init__(
        self,
        base_url: str,
        *,
        access_token: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        api_root = base_url.rstrip("/")
        if not api_root.endswith("/api/v1"):
            api_root = f"{api_root}/api/v1"
        headers = {"Accept": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        self._client = httpx.AsyncClient(
            base_url=f"{api_root}/",
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    @staticmethod
    def _resource_id(value: str, prefix: str) -> str:
        if not re.fullmatch(rf"{prefix}_[A-Za-z0-9_-]+", value):
            raise BeeFoundrySimApiError(f"Invalid BeeFoundrySim {prefix} resource ID")
        return value

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path.lstrip("/"), json=json)
        except httpx.RequestError as error:
            raise BeeFoundrySimApiError(f"BeeFoundrySim API unavailable: {error}") from error
        if response.is_error:
            try:
                payload = response.json()
                detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
            except ValueError:
                detail = response.text or response.reason_phrase
            raise BeeFoundrySimApiError(
                f"BeeFoundrySim API {method} {response.url.path} failed "
                f"({response.status_code}): {detail}"
            )
        if response.status_code == 204:
            return {"version": "v1", "status": "deleted"}
        try:
            payload = response.json()
        except ValueError as error:
            raise BeeFoundrySimApiError(
                f"BeeFoundrySim API returned non-JSON data for {method} {response.url.path}"
            ) from error
        if not isinstance(payload, dict):
            raise BeeFoundrySimApiError(
                f"BeeFoundrySim API returned an invalid object for {method} {response.url.path}"
            )
        return payload

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "health")

    async def create_project(self, name: str) -> dict[str, Any]:
        return await self._request("POST", "projects", json={"name": name})

    async def get_project(self, project_id: str) -> dict[str, Any]:
        project_id = self._resource_id(project_id, "prj")
        return await self._request("GET", f"projects/{project_id}")

    async def update_scene(self, project_id: str, scene: dict[str, Any]) -> dict[str, Any]:
        project_id = self._resource_id(project_id, "prj")
        return await self._request("PUT", f"projects/{project_id}/scene", json=scene)

    async def list_assets(self, project_id: str) -> dict[str, Any]:
        project_id = self._resource_id(project_id, "prj")
        return await self._request("GET", f"projects/{project_id}/assets")

    async def preflight(self, project_id: str) -> dict[str, Any]:
        project_id = self._resource_id(project_id, "prj")
        return await self._request("POST", f"projects/{project_id}/preflight")

    async def export_mjcf(self, project_id: str) -> dict[str, Any]:
        project_id = self._resource_id(project_id, "prj")
        return await self._request("POST", f"projects/{project_id}/exports/mjcf")

    async def create_simulation(self, project_id: str) -> dict[str, Any]:
        project_id = self._resource_id(project_id, "prj")
        return await self._request(
            "POST", "simulations", json={"project_id": project_id}
        )

    async def simulation_snapshot(self, simulation_id: str) -> dict[str, Any]:
        simulation_id = self._resource_id(simulation_id, "sim")
        return await self._request("GET", f"simulations/{simulation_id}/snapshot")

    async def simulation_command(
        self, simulation_id: str, command: str
    ) -> dict[str, Any]:
        simulation_id = self._resource_id(simulation_id, "sim")
        if command not in {"run", "pause", "step", "reset"}:
            raise BeeFoundrySimApiError("Invalid BeeFoundrySim simulation command")
        return await self._request("POST", f"simulations/{simulation_id}/{command}")

    async def stop_simulation(self, simulation_id: str) -> dict[str, Any]:
        simulation_id = self._resource_id(simulation_id, "sim")
        return await self._request("DELETE", f"simulations/{simulation_id}")

    async def set_simulation_speed(
        self, simulation_id: str, factor: float
    ) -> dict[str, Any]:
        simulation_id = self._resource_id(simulation_id, "sim")
        return await self._request(
            "PUT", f"simulations/{simulation_id}/speed", json={"factor": factor}
        )

    async def set_joint_targets(
        self, simulation_id: str, targets: dict[str, float]
    ) -> dict[str, Any]:
        simulation_id = self._resource_id(simulation_id, "sim")
        return await self._request(
            "PUT",
            f"simulations/{simulation_id}/joint-targets",
            json={"targets": targets},
        )

    async def set_actuator_controls(
        self, simulation_id: str, controls: dict[str, float]
    ) -> dict[str, Any]:
        simulation_id = self._resource_id(simulation_id, "sim")
        return await self._request(
            "PUT",
            f"simulations/{simulation_id}/actuator-controls",
            json={"controls": controls},
        )
