from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simlab.models.scene import Scene
from simlab.services.mjcf_exporter import export_scene_to_mjcf


@dataclass(slots=True)
class ActorSimulationState:
    actor_id: str
    position: list[float]
    quaternion: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.actor_id,
            "position": list(self.position),
            "quaternion": list(self.quaternion),
        }


@dataclass(slots=True)
class SimulationState:
    time: float
    actors: list[ActorSimulationState]

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "actors": [actor.to_dict() for actor in self.actors],
        }


class MuJoCoSimulationSession:
    """In-process MuJoCo session that exposes body poses keyed by SimLab actor id."""

    def __init__(
        self,
        scene: Scene,
        xml_path: str | Path,
        *,
        asset_root: str | Path | None = None,
    ) -> None:
        try:
            import mujoco
        except ImportError as exc:  # pragma: no cover - depends on optional runtime package
            msg = "MuJoCo is not installed. Install the 'mujoco' package to run simulations."
            raise RuntimeError(msg) from exc

        self._mujoco = mujoco
        self.scene = scene
        self.xml_path = export_scene_to_mjcf(scene, xml_path, asset_root=asset_root)
        self.model = mujoco.MjModel.from_xml_path(str(self.xml_path))
        self.data = mujoco.MjData(self.model)
        self._body_ids = self._map_actor_bodies(scene)
        mujoco.mj_forward(self.model, self.data)

    def step(self, steps: int = 1) -> SimulationState:
        for _ in range(max(steps, 1)):
            self._mujoco.mj_step(self.model, self.data)
        return self.state()

    def reset(self) -> SimulationState:
        self._mujoco.mj_resetData(self.model, self.data)
        self._mujoco.mj_forward(self.model, self.data)
        return self.state()

    def state(self) -> SimulationState:
        actor_states = []
        for actor_id, body_id in self._body_ids.items():
            actor_states.append(
                ActorSimulationState(
                    actor_id=actor_id,
                    position=[float(value) for value in self.data.xpos[body_id]],
                    quaternion=[float(value) for value in self.data.xquat[body_id]],
                )
            )
        return SimulationState(time=float(self.data.time), actors=actor_states)

    def _map_actor_bodies(self, scene: Scene) -> dict[str, int]:
        body_ids: dict[str, int] = {}
        for actor in scene.actors:
            body_id = self._mujoco.mj_name2id(
                self.model,
                self._mujoco.mjtObj.mjOBJ_BODY,
                actor.id,
            )
            if body_id >= 0:
                body_ids[actor.id] = body_id
        return body_ids
