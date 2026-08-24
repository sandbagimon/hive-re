from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from beefoundrysim.simulation.backend import SimulationBackend

BackendKind = Literal["local", "grpc"]


@dataclass(frozen=True, slots=True)
class BackendConfig:
    """Deployment-only backend selection; tasks never inspect this config."""

    kind: BackendKind = "local"
    target: str = "127.0.0.1:50051"
    token: str | None = None
    timeout: float = 10.0

    def __post_init__(self) -> None:
        if self.kind not in {"local", "grpc"}:
            raise ValueError("Backend kind must be 'local' or 'grpc'")
        if self.kind == "grpc" and not self.target:
            raise ValueError("Remote backend target must not be empty")
        if self.timeout <= 0:
            raise ValueError("Backend timeout must be > 0")

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> BackendConfig:
        return cls(
            kind=str(config.get("kind", "local")),  # type: ignore[arg-type]
            target=str(config.get("target", "127.0.0.1:50051")),
            token=(str(config["token"]) if config.get("token") is not None else None),
            timeout=float(config.get("timeout", 10.0)),
        )


def create_backend(config: BackendConfig | Mapping[str, Any]) -> SimulationBackend:
    """Create a local or remote backend without importing either into task code."""
    resolved = config if isinstance(config, BackendConfig) else BackendConfig.from_mapping(config)
    if resolved.kind == "local":
        from beefoundrysim.simulation.mujoco_backend import MujocoBackend

        return MujocoBackend()
    from beefoundrysim.simulation.grpc_backend import GrpcSimulationBackend

    return GrpcSimulationBackend(
        resolved.target,
        token=resolved.token,
        timeout=resolved.timeout,
    )
