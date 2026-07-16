from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from simlab.models.scene import Scene
from simlab.models.trajectory import JointTrajectory
from simlab.services.mjcf_exporter import export_scene_to_mjcf
from simlab.services.trajectory_player import (
    JointTrajectoryPlayer,
    TrajectoryPlaybackState,
)


class SimulationRuntimeError(RuntimeError):
    """Raised when MuJoCo publishes a non-finite runtime state."""


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
class ControllerSimulationState:
    status: str = "ready"
    message: str | None = None
    command_time: float | None = None
    timeout: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "command_time": self.command_time,
            "timeout": self.timeout,
        }


@dataclass(slots=True)
class SimulationState:
    time: float
    actors: list[ActorSimulationState]
    links: list[LinkSimulationState] = field(default_factory=list)
    joints: list[JointSimulationState] = field(default_factory=list)
    actuators: list[ActuatorSimulationState] = field(default_factory=list)
    controller: ControllerSimulationState = field(
        default_factory=ControllerSimulationState
    )
    trajectory: TrajectoryPlaybackState = field(
        default_factory=lambda: TrajectoryPlaybackState(
            status="stopped",
            time=0.0,
            duration=0.0,
            name=None,
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "actors": [actor.to_dict() for actor in self.actors],
            "links": [link.to_dict() for link in self.links],
            "joints": [joint.to_dict() for joint in self.joints],
            "actuators": [actuator.to_dict() for actuator in self.actuators],
            "controller": self.controller.to_dict(),
            "trajectory": self.trajectory.to_dict(),
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
        self._trajectory_player = JointTrajectoryPlayer()
        self._control_timeout = self._read_control_timeout(scene)
        self._controller_status = "ready"
        self._controller_message: str | None = None
        self._last_command_time: float | None = None
        self._reset_to_home()
        self._home_controls = self.data.ctrl.copy()
        mujoco.mj_forward(self.model, self.data)

    def step(self, steps: int = 1) -> SimulationState:
        for _ in range(max(steps, 1)):
            self._apply_trajectory_target()
            self._apply_control_watchdog()
            self._mujoco.mj_step(self.model, self.data)
        self._apply_trajectory_target()
        return self.state()

    def reset(self) -> SimulationState:
        self._reset_to_home()
        self._mujoco.mj_forward(self.model, self.data)
        return self.state()

    def set_joint_position_targets(self, targets: dict[str, float]) -> SimulationState:
        if self._trajectory_player.status == "playing":
            self._trajectory_player.pause(float(self.data.time))
        try:
            updates = self._validate_joint_position_targets(targets)
        except (TypeError, ValueError) as exc:
            self._controller_status = "fault"
            self._controller_message = str(exc)
            raise
        self._apply_joint_target_updates(updates)
        return self.state()

    def load_joint_trajectory(self, trajectory: JointTrajectory) -> SimulationState:
        self._trajectory_player.load(
            trajectory,
            allowed_joint_ids=set(self._joint_position_actuators),
        )
        targets = self._trajectory_player.sample(float(self.data.time))
        if targets is not None:
            self._apply_joint_target_updates(
                self._validate_joint_position_targets(targets)
            )
        return self.state()

    def play_trajectory(self) -> SimulationState:
        self._trajectory_player.play(float(self.data.time))
        self._apply_trajectory_target()
        return self.state()

    def pause_trajectory(self) -> SimulationState:
        self._trajectory_player.pause(float(self.data.time))
        return self.state()

    def stop_trajectory(self) -> SimulationState:
        self._trajectory_player.stop()
        targets = self._trajectory_player.sample(float(self.data.time))
        if targets is not None:
            self._apply_joint_target_updates(
                self._validate_joint_position_targets(targets)
            )
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
        state = SimulationState(
            time=float(self.data.time),
            actors=actor_states,
            links=link_states,
            joints=joint_states,
            actuators=actuator_states,
            controller=ControllerSimulationState(
                status=self._controller_status,
                message=self._controller_message,
                command_time=self._last_command_time,
                timeout=self._control_timeout or None,
            ),
            trajectory=self._trajectory_player.state(float(self.data.time)),
        )
        self._validate_finite_state(state)
        return state

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
        self._controller_status = "ready"
        self._controller_message = None
        self._last_command_time = None
        if self._trajectory_player.trajectory is not None:
            self._trajectory_player.stop()

    def _validate_joint_position_targets(
        self, targets: dict[str, float]
    ) -> list[tuple[int, float]]:
        updates: list[tuple[int, float]] = []
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
            updates.append((actuator_id, value))
        return updates

    def _apply_control_watchdog(self) -> None:
        if (
            self._control_timeout <= 0
            or self._controller_status != "active"
            or self._last_command_time is None
            or self.data.time - self._last_command_time < self._control_timeout
        ):
            return
        self.data.ctrl[:] = self._home_controls
        self._controller_status = "timed_out"
        self._controller_message = "Joint command timed out; targets returned to Home."

    def _apply_joint_target_updates(self, updates: list[tuple[int, float]]) -> None:
        for actuator_id, value in updates:
            self.data.ctrl[actuator_id] = value
        if updates:
            self._controller_status = "active"
            self._controller_message = None
            self._last_command_time = float(self.data.time)

    def _apply_trajectory_target(self) -> None:
        if self._trajectory_player.status != "playing":
            return
        targets = self._trajectory_player.sample(float(self.data.time))
        if targets is None:
            return
        self._apply_joint_target_updates(
            self._validate_joint_position_targets(targets)
        )

    @staticmethod
    def _read_control_timeout(scene: Scene) -> float:
        value = float(scene.simulation_config.get("control_timeout", 0.0))
        if not math.isfinite(value) or value < 0:
            raise ValueError("simulation_config.control_timeout must be finite and >= 0")
        return value

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

    def _validate_finite_state(self, state: SimulationState) -> None:
        invalid: str | None = None
        if not math.isfinite(state.time):
            invalid = "simulation time"
        for actor in state.actors:
            invalid = invalid or self._invalid_pose("actor", actor)
        for link in state.links:
            invalid = invalid or self._invalid_pose("link", link)
        for joint in state.joints:
            if not math.isfinite(joint.qpos):
                invalid = invalid or f"joint {joint.joint_id} qpos"
            if not math.isfinite(joint.qvel):
                invalid = invalid or f"joint {joint.joint_id} qvel"
        for actuator in state.actuators:
            if not math.isfinite(actuator.ctrl):
                invalid = invalid or f"actuator {actuator.actuator_id} ctrl"
            if not math.isfinite(actuator.force):
                invalid = invalid or f"actuator {actuator.actuator_id} force"
        if invalid is None:
            return
        message = f"MuJoCo produced a non-finite value for {invalid} at t={state.time}."
        self._controller_status = "fault"
        self._controller_message = message
        raise SimulationRuntimeError(message)

    @staticmethod
    def _invalid_pose(kind: str, state: ActorSimulationState) -> str | None:
        for field_name, values in (
            ("position", state.position),
            ("quaternion", state.quaternion),
        ):
            if not all(math.isfinite(value) for value in values):
                return f"{kind} {state.actor_id} {field_name}"
        return None
