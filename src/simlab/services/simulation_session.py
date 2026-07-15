from __future__ import annotations

import math
from dataclasses import dataclass, field
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
class LinkSimulationState(ActorSimulationState):
    pass


@dataclass(slots=True)
class JointSimulationState:
    joint_id: str
    qpos: float
    qvel: float

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.joint_id, "qpos": self.qpos, "qvel": self.qvel}


@dataclass(slots=True)
class ActuatorSimulationState:
    actuator_id: str
    ctrl: float
    force: float

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.actuator_id, "ctrl": self.ctrl, "force": self.force}


@dataclass(slots=True)
class SimulationState:
    time: float
    actors: list[ActorSimulationState]
    links: list[LinkSimulationState] = field(default_factory=list)
    joints: list[JointSimulationState] = field(default_factory=list)
    actuators: list[ActuatorSimulationState] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "actors": [actor.to_dict() for actor in self.actors],
            "links": [link.to_dict() for link in self.links],
            "joints": [joint.to_dict() for joint in self.joints],
            "actuators": [actuator.to_dict() for actuator in self.actuators],
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
        self._link_ids, self._joint_ids, self._actuator_ids = self._map_robotics(scene)
        self._joint_position_actuators = self._map_joint_position_actuators(scene)
        self._reset_to_home()
        mujoco.mj_forward(self.model, self.data)

    def step(self, steps: int = 1) -> SimulationState:
        for _ in range(max(steps, 1)):
            self._mujoco.mj_step(self.model, self.data)
        return self.state()

    def reset(self) -> SimulationState:
        self._reset_to_home()
        self._mujoco.mj_forward(self.model, self.data)
        return self.state()

    def set_joint_position_targets(self, targets: dict[str, float]) -> SimulationState:
        for joint_id, target in targets.items():
            actuator_id = self._joint_position_actuators.get(joint_id)
            if actuator_id is None:
                raise ValueError(f"No position actuator is mapped to joint: {joint_id}")
            value = float(target)
            if not math.isfinite(value):
                raise ValueError(f"Joint target must be finite: {joint_id}")
            if self.model.actuator_ctrllimited[actuator_id]:
                lower, upper = self.model.actuator_ctrlrange[actuator_id]
                value = max(float(lower), min(float(upper), value))
            self.data.ctrl[actuator_id] = value
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
        link_states = [
            LinkSimulationState(
                actor_id=link_id,
                position=[float(value) for value in self.data.xpos[body_id]],
                quaternion=[float(value) for value in self.data.xquat[body_id]],
            )
            for link_id, body_id in self._link_ids.items()
        ]
        joint_states = [
            JointSimulationState(
                joint_id=joint_id,
                qpos=float(self.data.qpos[self.model.jnt_qposadr[mujoco_id]]),
                qvel=float(self.data.qvel[self.model.jnt_dofadr[mujoco_id]]),
            )
            for joint_id, mujoco_id in self._joint_ids.items()
        ]
        actuator_states = [
            ActuatorSimulationState(
                actuator_id=actuator_id,
                ctrl=float(self.data.ctrl[mujoco_id]),
                force=float(self.data.actuator_force[mujoco_id]),
            )
            for actuator_id, mujoco_id in self._actuator_ids.items()
        ]
        return SimulationState(
            time=float(self.data.time),
            actors=actor_states,
            links=link_states,
            joints=joint_states,
            actuators=actuator_states,
        )

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

    def _map_robotics(self, scene: Scene) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
        links: dict[str, int] = {}
        joints: dict[str, int] = {}
        actuators: dict[str, int] = {}
        if scene.robotics is None:
            return links, joints, actuators
        for articulation in scene.robotics.articulations:
            for link in articulation.links:
                identifier = self._mujoco.mj_name2id(
                    self.model, self._mujoco.mjtObj.mjOBJ_BODY, link.id
                )
                if identifier >= 0:
                    links[link.id] = identifier
            for joint in articulation.joints:
                identifier = self._mujoco.mj_name2id(
                    self.model, self._mujoco.mjtObj.mjOBJ_JOINT, joint.id
                )
                if identifier >= 0:
                    joints[joint.id] = identifier
            for actuator in articulation.actuators:
                identifier = self._mujoco.mj_name2id(
                    self.model, self._mujoco.mjtObj.mjOBJ_ACTUATOR, actuator.id
                )
                if identifier >= 0:
                    actuators[actuator.id] = identifier
        return links, joints, actuators

    def _reset_to_home(self) -> None:
        key_id = self._mujoco.mj_name2id(
            self.model, self._mujoco.mjtObj.mjOBJ_KEY, "home"
        )
        if key_id >= 0:
            self._mujoco.mj_resetDataKeyframe(self.model, self.data, key_id)
        else:
            self._mujoco.mj_resetData(self.model, self.data)

    def _map_joint_position_actuators(self, scene: Scene) -> dict[str, int]:
        result: dict[str, int] = {}
        if scene.robotics is None:
            return result
        for articulation in scene.robotics.articulations:
            for actuator in articulation.actuators:
                if actuator.control_type != "position":
                    continue
                mujoco_id = self._actuator_ids.get(actuator.id)
                if mujoco_id is not None:
                    result[actuator.joint_id] = mujoco_id
        return result
