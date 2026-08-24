from __future__ import annotations

from importlib import metadata

from beefoundrysim.simulation.runtime import EngineCapability, EngineDescriptor


def mujoco_engine_descriptor(version: str | None = None) -> EngineDescriptor:
    """Return MuJoCo metadata without importing the native runtime module."""

    if version is None:
        try:
            version = metadata.version("mujoco")
        except metadata.PackageNotFoundError:
            version = "not-installed"
    return EngineDescriptor(
        id="mujoco",
        name="MuJoCo",
        version=version,
        capabilities=frozenset(
            {
                EngineCapability.RIGID_BODY,
                EngineCapability.ARTICULATION,
                EngineCapability.COLLISION,
                EngineCapability.CONSTRAINT,
                EngineCapability.EXTERNAL_FORCE,
                EngineCapability.RAY_QUERY,
                EngineCapability.KINEMATIC_ACTOR,
            }
        ),
    )
