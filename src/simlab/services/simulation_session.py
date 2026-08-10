from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import numpy as np

from simlab.models.attachment import Attachment
from simlab.models.recording import JointStateRecording
from simlab.models.scene import Scene
from simlab.models.trajectory import JointTrajectory
from simlab.services.contact_sensors import ContactSensorSample, ContactSensorScheduler
from simlab.services.controller_runtime import (
    ActuatorObservation,
    AttachmentObservation,
    BodyObservation,
    ControllerObservation,
    ControllerRunner,
    JointObservation,
    NavigationUpdate,
    RangefinderObservation,
    StepController,
)
from simlab.services.imu_sensors import ImuKinematics, ImuSensorSample, ImuSensorScheduler
from simlab.services.joint_state_recorder import JointStateRecorder
from simlab.services.joint_state_sensors import (
    JointKinematics,
    JointStateSensorSample,
    JointStateSensorScheduler,
)
from simlab.services.mjcf_exporter import (
    attachment_constraint_name,
    attachment_site_names,
    export_scene_to_mjcf,
    imu_sensor_channel_names,
    rangefinder_sensor_name,
)
from simlab.services.mujoco_contact_adapter import MujocoContactAggregator
from simlab.services.quadrotor_dynamics import quadrotor_models_from_scene
from simlab.services.rangefinder_sensors import (
    RangefinderMeasurement,
    RangefinderSensorSample,
    RangefinderSensorScheduler,
)
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


@dataclass(frozen=True, slots=True)
class AttachmentSimulationState:
    attachment_id: str
    status: str
    active: bool
    requested_active: bool
    eligible: bool
    contact: bool
    distance: float
    relative_speed: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.attachment_id,
            "status": self.status,
            "active": self.active,
            "requested_active": self.requested_active,
            "eligible": self.eligible,
            "contact": self.contact,
            "distance": self.distance,
            "relative_speed": self.relative_speed,
        }


@dataclass(frozen=True, slots=True)
class DeliveryTaskSimulationState:
    task_id: str
    status: str
    attachment_id: str
    payload_body_id: str
    distance_to_dropoff: float
    payload_speed: float
    stable_time: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.task_id,
            "status": self.status,
            "attachment_id": self.attachment_id,
            "payload_body_id": self.payload_body_id,
            "distance_to_dropoff": self.distance_to_dropoff,
            "payload_speed": self.payload_speed,
            "stable_time": self.stable_time,
        }


@dataclass(frozen=True, slots=True)
class _AttachmentBinding:
    definition: Attachment
    equality_id: int
    parent_site_id: int
    child_site_id: int
    parent_body_id: int
    child_body_id: int


@dataclass(slots=True)
class ControllerSimulationState:
    status: str = "ready"
    message: str | None = None
    command_time: float | None = None
    timeout: float | None = None
    mode: str = "manual"
    name: str | None = None
    step_count: int = 0
    last_duration: float | None = None
    deadline: float | None = None
    reset_deadline: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "command_time": self.command_time,
            "timeout": self.timeout,
            "mode": self.mode,
            "name": self.name,
            "step_count": self.step_count,
            "last_duration": self.last_duration,
            "deadline": self.deadline,
            "reset_deadline": self.reset_deadline,
        }


@dataclass(frozen=True, slots=True)
class NavigationSimulationState:
    status: str = "idle"
    route: tuple[tuple[float, float, float], ...] = ()
    route_revision: int = 0
    map_revision: int = 0
    replan_count: int = 0
    occupied_cell_count: int = 0
    last_replan_time: float | None = None
    message: str | None = None

    @classmethod
    def from_update(cls, update: NavigationUpdate) -> NavigationSimulationState:
        return cls(
            status=update.status,
            route=update.route,
            route_revision=update.route_revision,
            map_revision=update.map_revision,
            replan_count=update.replan_count,
            occupied_cell_count=update.occupied_cell_count,
            last_replan_time=update.last_replan_time,
            message=update.message,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "route": [list(point) for point in self.route],
            "route_revision": self.route_revision,
            "map_revision": self.map_revision,
            "replan_count": self.replan_count,
            "occupied_cell_count": self.occupied_cell_count,
            "last_replan_time": self.last_replan_time,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class RecordingSimulationState:
    active: bool = False
    sample_count: int = 0
    sensor_event_count: int = 0
    limit_reached: bool = False
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "sample_count": self.sample_count,
            "sensor_event_count": self.sensor_event_count,
            "limit_reached": self.limit_reached,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class ClockSimulationState:
    target_rtf: float = 1.0
    actual_rtf: float = 0.0
    timestep: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "target_rtf": self.target_rtf,
            "actual_rtf": self.actual_rtf,
            "timestep": self.timestep,
        }


@dataclass(slots=True)
class SimulationState:
    time: float
    actors: list[ActorSimulationState]
    links: list[LinkSimulationState] = field(default_factory=list)
    joints: list[JointSimulationState] = field(default_factory=list)
    actuators: list[ActuatorSimulationState] = field(default_factory=list)
    attachments: list[AttachmentSimulationState] = field(default_factory=list)
    delivery_tasks: list[DeliveryTaskSimulationState] = field(default_factory=list)
    sensors: list[
        JointStateSensorSample
        | ImuSensorSample
        | ContactSensorSample
        | RangefinderSensorSample
    ] = field(default_factory=list)
    controller: ControllerSimulationState = field(default_factory=ControllerSimulationState)
    navigation: NavigationSimulationState = field(
        default_factory=NavigationSimulationState
    )
    trajectory: TrajectoryPlaybackState = field(
        default_factory=lambda: TrajectoryPlaybackState(
            status="stopped",
            time=0.0,
            duration=0.0,
            name=None,
        )
    )
    recording: RecordingSimulationState = field(default_factory=RecordingSimulationState)
    clock: ClockSimulationState = field(default_factory=ClockSimulationState)

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "actors": [actor.to_dict() for actor in self.actors],
            "links": [link.to_dict() for link in self.links],
            "joints": [joint.to_dict() for joint in self.joints],
            "actuators": [actuator.to_dict() for actuator in self.actuators],
            "attachments": [attachment.to_dict() for attachment in self.attachments],
            "delivery_tasks": [task.to_dict() for task in self.delivery_tasks],
            "sensors": [sensor.to_dict() for sensor in self.sensors],
            "controller": self.controller.to_dict(),
            "navigation": self.navigation.to_dict(),
            "trajectory": self.trajectory.to_dict(),
            "recording": self.recording.to_dict(),
            "clock": self.clock.to_dict(),
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
        self._attachment_bindings = self._map_attachments(scene)
        self._attachment_requests = {
            item.id: item.initially_active for item in scene.attachments
        }
        self._attachment_eligible_since: dict[str, float] = {}
        self._delivery_picked = {item.id: False for item in scene.delivery_tasks}
        self._delivery_settle_since: dict[str, float] = {}
        self._delivery_completed = {item.id: False for item in scene.delivery_tasks}
        self._joint_position_actuators = self._map_joint_position_actuators(scene)
        self._quadrotor_models = quadrotor_models_from_scene(scene)
        self._validate_quadrotor_bindings()
        self._trajectory_player = JointTrajectoryPlayer()
        self._state_recorder = JointStateRecorder(self._read_recording_max_samples(scene))
        sensor_definitions = [
            sensor
            for articulation in (scene.robotics.articulations if scene.robotics else [])
            for sensor in articulation.sensors
        ]
        self._sensor_types = {
            sensor.id: sensor.sensor_type
            for sensor in sensor_definitions
            if sensor.sensor_type in {"joint_state", "imu", "contact", "rangefinder"}
        }
        self._sensor_ids = set(self._sensor_types)
        self._joint_state_sensors = JointStateSensorScheduler(
            sensor_definitions,
            float(self.model.opt.timestep),
        )
        self._imu_sensor_definitions = [
            sensor for sensor in sensor_definitions if sensor.sensor_type == "imu"
        ]
        self._imu_sensors = ImuSensorScheduler(
            self._imu_sensor_definitions,
            float(self.model.opt.timestep),
        )
        self._imu_channel_addresses = self._map_imu_sensor_channels()
        self._contact_sensor_definitions = [
            sensor for sensor in sensor_definitions if sensor.sensor_type == "contact"
        ]
        self._contact_sensors = ContactSensorScheduler(
            self._contact_sensor_definitions,
            float(self.model.opt.timestep),
        )
        self._contact_aggregator = MujocoContactAggregator(
            self._mujoco,
            self.model,
            self.data,
            scene.robotics,
            float(self.model.opt.timestep),
        )
        self._rangefinder_sensor_definitions = [
            sensor for sensor in sensor_definitions if sensor.sensor_type == "rangefinder"
        ]
        self._rangefinder_sensors = RangefinderSensorScheduler(
            self._rangefinder_sensor_definitions,
            float(self.model.opt.timestep),
        )
        self._rangefinder_addresses = self._map_rangefinder_sensor_channels()
        self._physics_step_index = 0
        self._controller_runner = ControllerRunner(
            deadline=self._read_controller_deadline(scene),
            reset_deadline=self._read_controller_reset_deadline(scene),
        )
        self._control_timeout = self._read_control_timeout(scene)
        self._controller_status = "ready"
        self._controller_message: str | None = None
        self._last_command_time: float | None = None
        self._navigation_state = NavigationSimulationState()
        self._reset_to_home()
        self._home_controls = self.data.ctrl.copy()
        mujoco.mj_forward(self.model, self.data)
        self._reset_sensors()

    def step(self, steps: int = 1) -> SimulationState:
        for _ in range(max(steps, 1)):
            self._apply_trajectory_target()
            self._apply_python_controller()
            self._update_attachment_constraints()
            self._apply_control_watchdog()
            self._apply_quadrotor_forces()
            self._mujoco.mj_step(self.model, self.data)
            self._apply_trajectory_target()
            self._physics_step_index += 1
            self._update_delivery_tasks()
            emitted_sensors = self._joint_state_sensors.capture(
                self._physics_step_index,
                float(self.data.time),
                self._joint_kinematics(),
            )
            emitted_imu_sensors = self._imu_sensors.capture(
                self._physics_step_index,
                float(self.data.time),
                self._imu_measurements(),
            )
            emitted_contact_sensors = self._contact_sensors.capture(
                self._physics_step_index,
                float(self.data.time),
                self._contact_aggregator.measurements(),
            )
            emitted_rangefinder_sensors = self._rangefinder_sensors.capture(
                self._physics_step_index,
                float(self.data.time),
                self._rangefinder_measurements(),
            )
            if self._state_recorder.active:
                recording_sensors: list[
                    JointStateSensorSample
                    | ImuSensorSample
                    | ContactSensorSample
                    | RangefinderSensorSample
                ] = [
                    *emitted_sensors,
                    *emitted_imu_sensors,
                    *emitted_contact_sensors,
                    *emitted_rangefinder_sensors,
                ]
                self._state_recorder.capture(
                    self.state(),
                    recording_sensors,
                )
        return self.state()

    def reset(self) -> SimulationState:
        if self._state_recorder.active:
            self._state_recorder.stop()
        self._reset_to_home()
        self._mujoco.mj_forward(self.model, self.data)
        self._reset_sensors()
        self._navigation_state = NavigationSimulationState()
        if self._controller_runner.enabled:
            self._controller_runner.reset(self._controller_observation())
            self._sync_python_controller_state()
        return self.state()

    def attach_controller(
        self,
        controller: StepController,
        *,
        name: str | None = None,
    ) -> SimulationState:
        if self._trajectory_player.status == "playing":
            raise RuntimeError("Pause or stop the trajectory before attaching a controller")
        self._controller_runner.attach(controller, name=name)
        self._navigation_state = NavigationSimulationState()
        self._controller_runner.reset(self._controller_observation())
        self._sync_python_controller_state()
        return self.state()

    def detach_controller(self) -> SimulationState:
        self._controller_runner.detach()
        self._controller_status = "ready"
        self._controller_message = None
        self._last_command_time = None
        self._navigation_state = NavigationSimulationState()
        return self.state()

    def set_joint_position_targets(self, targets: dict[str, float]) -> SimulationState:
        if self._controller_runner.attached:
            raise RuntimeError("Detach the Python controller before setting manual targets")
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

    def set_actuator_controls(self, controls: dict[str, float]) -> SimulationState:
        """Apply named actuator values without exposing engine indexes."""

        if self._controller_runner.attached:
            raise RuntimeError("Detach the Python controller before setting manual controls")
        if self._trajectory_player.status == "playing":
            self._trajectory_player.pause(float(self.data.time))
        try:
            updates = self._validate_actuator_controls(controls)
        except (TypeError, ValueError) as exc:
            self._controller_status = "fault"
            self._controller_message = str(exc)
            raise
        self._apply_actuator_control_updates(updates)
        return self.state()

    def set_attachment_commands(self, commands: dict[str, bool]) -> SimulationState:
        """Request runtime attachment activation without exposing MuJoCo equality indexes."""

        if self._controller_runner.attached:
            raise RuntimeError("Detach the Python controller before setting attachment commands")
        updates = self._validate_attachment_commands(commands)
        self._apply_attachment_command_updates(updates)
        self._update_attachment_constraints()
        self._mujoco.mj_forward(self.model, self.data)
        return self.state()

    def load_joint_trajectory(self, trajectory: JointTrajectory) -> SimulationState:
        self._trajectory_player.load(
            trajectory,
            allowed_joint_ids=set(self._joint_position_actuators),
        )
        targets = self._trajectory_player.sample(float(self.data.time))
        if targets is not None:
            self._apply_joint_target_updates(self._validate_joint_position_targets(targets))
        return self.state()

    def play_trajectory(self) -> SimulationState:
        if self._controller_runner.attached:
            raise RuntimeError("Detach the Python controller before playing a trajectory")
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
            self._apply_joint_target_updates(self._validate_joint_position_targets(targets))
        return self.state()

    def start_joint_recording(
        self,
        *,
        name: str,
        joint_ids: list[str] | None = None,
        actuator_ids: list[str] | None = None,
        sensor_ids: list[str] | None = None,
    ) -> SimulationState:
        selected_joint_ids = joint_ids if joint_ids is not None else list(self._joint_ids)
        selected_actuator_ids = (
            actuator_ids if actuator_ids is not None else list(self._actuator_ids)
        )
        selected_sensor_ids = sensor_ids or []
        unknown_sensor_ids = sorted(set(selected_sensor_ids) - self._sensor_ids)
        if unknown_sensor_ids:
            raise ValueError(
                "Recording references unknown sensor ID(s): " + ", ".join(unknown_sensor_ids)
            )
        self._state_recorder.start(
            name=name,
            joint_ids=selected_joint_ids,
            actuator_ids=selected_actuator_ids,
            sensor_ids=selected_sensor_ids,
            sensor_types={
                sensor_id: self._sensor_types[sensor_id] for sensor_id in selected_sensor_ids
            },
            timestep=float(self.model.opt.timestep),
            scene_version=self.scene.version,
            engine_version=str(self._mujoco.__version__),
        )
        initial_sensor_samples: list[
            JointStateSensorSample
            | ImuSensorSample
            | ContactSensorSample
            | RangefinderSensorSample
        ] = []
        if math.isclose(float(self.data.time), 0.0, abs_tol=1e-12):
            initial_sensor_samples = [
                *self._joint_state_sensors.latest_samples,
                *self._imu_sensors.latest_samples,
                *self._contact_sensors.latest_samples,
                *self._rangefinder_sensors.latest_samples,
            ]
        self._state_recorder.capture(self.state(), initial_sensor_samples)
        return self.state()

    def stop_joint_recording(self) -> tuple[SimulationState, JointStateRecording]:
        recording = self._state_recorder.stop()
        return self.state(), recording

    @property
    def joint_recording(self) -> JointStateRecording | None:
        return self._state_recorder.recording

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
            attachments=self._attachment_states(),
            delivery_tasks=self._delivery_task_states(),
            sensors=[
                *self._joint_state_sensors.latest_samples,
                *self._imu_sensors.latest_samples,
                *self._contact_sensors.latest_samples,
                *self._rangefinder_sensors.latest_samples,
            ],
            controller=ControllerSimulationState(
                status=self._controller_status,
                message=self._controller_message,
                command_time=self._last_command_time,
                timeout=self._control_timeout or None,
                mode="python" if self._controller_runner.attached else "manual",
                name=self._controller_runner.state.name,
                step_count=self._controller_runner.state.step_count,
                last_duration=self._controller_runner.state.last_duration,
                deadline=self._controller_runner.state.deadline,
                reset_deadline=self._controller_runner.state.reset_deadline,
            ),
            navigation=self._navigation_state,
            trajectory=self._trajectory_player.state(float(self.data.time)),
            recording=self._recording_state(),
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

    def _map_attachments(self, scene: Scene) -> dict[str, _AttachmentBinding]:
        bindings: dict[str, _AttachmentBinding] = {}
        body_ids = {**self._body_ids, **self._link_ids}
        for attachment in scene.attachments:
            equality_id = self._mujoco.mj_name2id(
                self.model,
                self._mujoco.mjtObj.mjOBJ_EQUALITY,
                attachment_constraint_name(attachment.id),
            )
            parent_site_name, child_site_name = attachment_site_names(attachment.id)
            parent_site_id = self._mujoco.mj_name2id(
                self.model, self._mujoco.mjtObj.mjOBJ_SITE, parent_site_name
            )
            child_site_id = self._mujoco.mj_name2id(
                self.model, self._mujoco.mjtObj.mjOBJ_SITE, child_site_name
            )
            parent_body_id = body_ids.get(attachment.parent_body_id, -1)
            child_body_id = body_ids.get(attachment.child_body_id, -1)
            if min(
                equality_id,
                parent_site_id,
                child_site_id,
                parent_body_id,
                child_body_id,
            ) < 0:
                raise ValueError(f"Attachment was not exported to MuJoCo: {attachment.id}")
            bindings[attachment.id] = _AttachmentBinding(
                definition=attachment,
                equality_id=equality_id,
                parent_site_id=parent_site_id,
                child_site_id=child_site_id,
                parent_body_id=parent_body_id,
                child_body_id=child_body_id,
            )
        return bindings

    def _reset_to_home(self) -> None:
        key_id = self._mujoco.mj_name2id(self.model, self._mujoco.mjtObj.mjOBJ_KEY, "home")
        if key_id >= 0:
            self._mujoco.mj_resetDataKeyframe(self.model, self.data, key_id)
        else:
            self._mujoco.mj_resetData(self.model, self.data)
        self._reset_attachments()
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

    def _validate_actuator_controls(self, controls: dict[str, float]) -> list[tuple[int, float]]:
        updates: list[tuple[int, float]] = []
        for actuator_id, control in controls.items():
            mujoco_id = self._actuator_ids.get(actuator_id)
            if mujoco_id is None:
                raise ValueError(f"Unknown actuator: {actuator_id}")
            value = float(control)
            if not math.isfinite(value):
                raise ValueError(f"Actuator control must be finite: {actuator_id}")
            if self.model.actuator_ctrllimited[mujoco_id]:
                lower, upper = self.model.actuator_ctrlrange[mujoco_id]
                value = max(float(lower), min(float(upper), value))
            updates.append((mujoco_id, value))
        return updates

    def _validate_attachment_commands(self, commands: dict[str, bool]) -> list[tuple[str, bool]]:
        updates: list[tuple[str, bool]] = []
        for attachment_id, active in commands.items():
            if attachment_id not in self._attachment_bindings:
                raise ValueError(f"Unknown attachment: {attachment_id}")
            if not isinstance(active, bool):
                raise ValueError(f"Attachment command must be boolean: {attachment_id}")
            updates.append((attachment_id, active))
        return updates

    def _apply_control_watchdog(self) -> None:
        if (
            self._controller_runner.attached
            or self._control_timeout <= 0
            or self._controller_status != "active"
            or self._last_command_time is None
            or self.data.time - self._last_command_time < self._control_timeout
        ):
            return
        self.data.ctrl[:] = self._home_controls
        self._controller_status = "timed_out"
        self._controller_message = "Control command timed out; actuators returned to Home."

    def _apply_joint_target_updates(self, updates: list[tuple[int, float]]) -> None:
        self._apply_actuator_control_updates(updates)

    def _apply_actuator_control_updates(self, updates: list[tuple[int, float]]) -> None:
        for actuator_id, value in updates:
            self.data.ctrl[actuator_id] = value
        if updates:
            self._controller_status = "active"
            self._controller_message = None
            self._last_command_time = float(self.data.time)

    def _apply_attachment_command_updates(self, updates: list[tuple[str, bool]]) -> None:
        for attachment_id, active in updates:
            self._attachment_requests[attachment_id] = active
            if active:
                continue
            binding = self._attachment_bindings[attachment_id]
            self.data.eq_active[binding.equality_id] = False
            self._attachment_eligible_since.pop(attachment_id, None)

    def _reset_attachments(self) -> None:
        self._attachment_eligible_since.clear()
        for task_id in self._delivery_picked:
            self._delivery_picked[task_id] = False
            self._delivery_completed[task_id] = False
        self._delivery_settle_since.clear()
        for attachment_id, binding in self._attachment_bindings.items():
            active = binding.definition.initially_active
            self._attachment_requests[attachment_id] = active
            self.data.eq_active[binding.equality_id] = active

    def _update_attachment_constraints(self) -> None:
        now = float(self.data.time)
        for attachment_id, binding in self._attachment_bindings.items():
            if not self._attachment_requests[attachment_id]:
                self.data.eq_active[binding.equality_id] = False
                self._attachment_eligible_since.pop(attachment_id, None)
                continue
            if bool(self.data.eq_active[binding.equality_id]):
                continue
            observation = self._attachment_observation(binding)
            if not observation.eligible:
                self._attachment_eligible_since.pop(attachment_id, None)
                continue
            eligible_since = self._attachment_eligible_since.setdefault(attachment_id, now)
            if now - eligible_since + 1e-12 >= binding.definition.capture_duration:
                self.data.eq_active[binding.equality_id] = True
                self._attachment_eligible_since.pop(attachment_id, None)

    def _attachment_observation(self, binding: _AttachmentBinding) -> AttachmentObservation:
        parent_position = self.data.site_xpos[binding.parent_site_id]
        child_position = self.data.site_xpos[binding.child_site_id]
        distance = float(np.linalg.norm(parent_position - child_position))
        parent_velocity = self._object_velocity(
            self._mujoco.mjtObj.mjOBJ_SITE, binding.parent_site_id
        )
        child_velocity = self._object_velocity(
            self._mujoco.mjtObj.mjOBJ_SITE, binding.child_site_id
        )
        relative_speed = float(np.linalg.norm(parent_velocity - child_velocity))
        contact = self._bodies_in_contact(binding.parent_body_id, binding.child_body_id)
        definition = binding.definition
        eligible = (
            distance <= definition.capture_distance
            and relative_speed <= definition.capture_speed
            and (contact or not definition.require_contact)
        )
        return AttachmentObservation(
            active=bool(self.data.eq_active[binding.equality_id]),
            requested_active=self._attachment_requests[binding.definition.id],
            eligible=eligible,
            contact=contact,
            distance=distance,
            relative_speed=relative_speed,
        )

    def _attachment_observations(self) -> dict[str, AttachmentObservation]:
        return {
            attachment_id: self._attachment_observation(binding)
            for attachment_id, binding in self._attachment_bindings.items()
        }

    def _attachment_states(self) -> list[AttachmentSimulationState]:
        result: list[AttachmentSimulationState] = []
        for attachment_id, observation in self._attachment_observations().items():
            status = (
                "active"
                if observation.active
                else "pending"
                if observation.requested_active
                else "inactive"
            )
            result.append(
                AttachmentSimulationState(
                    attachment_id=attachment_id,
                    status=status,
                    active=observation.active,
                    requested_active=observation.requested_active,
                    eligible=observation.eligible,
                    contact=observation.contact,
                    distance=observation.distance,
                    relative_speed=observation.relative_speed,
                )
            )
        return result

    def _bodies_in_contact(self, first_body_id: int, second_body_id: int) -> bool:
        expected = {first_body_id, second_body_id}
        for index in range(int(self.data.ncon)):
            contact = self.data.contact[index]
            bodies = {
                int(self.model.geom_bodyid[int(contact.geom1)]),
                int(self.model.geom_bodyid[int(contact.geom2)]),
            }
            if bodies == expected:
                return True
        return False

    def _object_velocity(self, object_type: Any, object_id: int) -> np.ndarray[Any, Any]:
        velocity = np.zeros(6, dtype=np.float64)
        self._mujoco.mj_objectVelocity(
            self.model,
            self.data,
            object_type,
            object_id,
            velocity,
            0,
        )
        return velocity[3:]

    def _update_delivery_tasks(self) -> None:
        now = float(self.data.time)
        body_ids = {**self._body_ids, **self._link_ids}
        for task in self.scene.delivery_tasks:
            binding = self._attachment_bindings[task.attachment_id]
            if bool(self.data.eq_active[binding.equality_id]):
                self._delivery_picked[task.id] = True
                self._delivery_settle_since.pop(task.id, None)
                continue
            if not self._delivery_picked[task.id] or self._delivery_completed[task.id]:
                continue
            body_id = body_ids[task.payload_body_id]
            distance = float(
                np.linalg.norm(self.data.xpos[body_id] - np.asarray(task.dropoff_position))
            )
            speed = float(
                np.linalg.norm(
                    self._object_velocity(self._mujoco.mjtObj.mjOBJ_BODY, body_id)
                )
            )
            if distance > task.position_tolerance or speed > task.settle_speed:
                self._delivery_settle_since.pop(task.id, None)
                continue
            settled_since = self._delivery_settle_since.setdefault(task.id, now)
            if now - settled_since + 1e-12 >= task.settle_duration:
                self._delivery_completed[task.id] = True

    def _delivery_task_states(self) -> list[DeliveryTaskSimulationState]:
        body_ids = {**self._body_ids, **self._link_ids}
        now = float(self.data.time)
        result: list[DeliveryTaskSimulationState] = []
        for task in self.scene.delivery_tasks:
            binding = self._attachment_bindings[task.attachment_id]
            active = bool(self.data.eq_active[binding.equality_id])
            body_id = body_ids[task.payload_body_id]
            distance = float(
                np.linalg.norm(self.data.xpos[body_id] - np.asarray(task.dropoff_position))
            )
            speed = float(
                np.linalg.norm(
                    self._object_velocity(self._mujoco.mjtObj.mjOBJ_BODY, body_id)
                )
            )
            settled_since = self._delivery_settle_since.get(task.id)
            stable_time = max(0.0, now - settled_since) if settled_since is not None else 0.0
            if self._delivery_completed[task.id]:
                status = "completed"
            elif active:
                status = "in_transit"
            elif settled_since is not None:
                status = "settling"
            elif self._delivery_picked[task.id]:
                status = "released"
            else:
                status = "waiting_pickup"
            result.append(
                DeliveryTaskSimulationState(
                    task_id=task.id,
                    status=status,
                    attachment_id=task.attachment_id,
                    payload_body_id=task.payload_body_id,
                    distance_to_dropoff=distance,
                    payload_speed=speed,
                    stable_time=stable_time,
                )
            )
        return result

    def _apply_trajectory_target(self) -> None:
        if self._trajectory_player.status != "playing":
            return
        targets = self._trajectory_player.sample(float(self.data.time))
        if targets is None:
            return
        self._apply_joint_target_updates(self._validate_joint_position_targets(targets))

    def _controller_observation(self) -> ControllerObservation:
        joints = {
            joint_id: JointObservation(
                qpos=float(self.data.qpos[self.model.jnt_qposadr[mujoco_id]]),
                qvel=float(self.data.qvel[self.model.jnt_dofadr[mujoco_id]]),
            )
            for joint_id, mujoco_id in self._joint_ids.items()
        }
        actuators = {
            actuator_id: ActuatorObservation(
                ctrl=float(self.data.ctrl[mujoco_id]),
                force=float(self.data.actuator_force[mujoco_id]),
            )
            for actuator_id, mujoco_id in self._actuator_ids.items()
        }
        body_ids = {**self._body_ids, **self._link_ids}
        bodies: dict[str, BodyObservation] = {}
        for body_id, mujoco_id in body_ids.items():
            velocity = np.zeros(6, dtype=np.float64)
            self._mujoco.mj_objectVelocity(
                self.model,
                self.data,
                self._mujoco.mjtObj.mjOBJ_BODY,
                mujoco_id,
                velocity,
                0,
            )
            bodies[body_id] = BodyObservation(
                position=cast(
                    tuple[float, float, float],
                    tuple(float(value) for value in self.data.xpos[mujoco_id]),
                ),
                quaternion=cast(
                    tuple[float, float, float, float],
                    tuple(float(value) for value in self.data.xquat[mujoco_id]),
                ),
                linear_velocity=cast(
                    tuple[float, float, float],
                    tuple(float(value) for value in velocity[3:]),
                ),
                angular_velocity=cast(
                    tuple[float, float, float],
                    tuple(float(value) for value in velocity[:3]),
                ),
            )
        return ControllerObservation(
            time=float(self.data.time),
            timestep=float(self.model.opt.timestep),
            joints=joints,
            actuators=actuators,
            bodies=bodies,
            attachments=self._attachment_observations(),
            rangefinders={
                sample.sensor_id: RangefinderObservation(
                    distance=sample.distance,
                    max_distance=sample.max_distance,
                    hit=sample.hit,
                )
                for sample in self._rangefinder_sensors.latest_samples
            },
        )

    def _joint_kinematics(self) -> dict[str, JointKinematics]:
        return {
            joint_id: JointKinematics(
                qpos=float(self.data.qpos[self.model.jnt_qposadr[mujoco_id]]),
                qvel=float(self.data.qvel[self.model.jnt_dofadr[mujoco_id]]),
            )
            for joint_id, mujoco_id in self._joint_ids.items()
        }

    def _reset_sensors(self) -> None:
        self._physics_step_index = 0
        self._joint_state_sensors.reset(
            float(self.data.time),
            self._joint_kinematics(),
        )
        self._imu_sensors.reset(
            float(self.data.time),
            self._imu_measurements(),
        )
        self._contact_sensors.reset(
            float(self.data.time),
            self._contact_aggregator.measurements(),
        )
        self._rangefinder_sensors.reset(
            float(self.data.time),
            self._rangefinder_measurements(),
        )

    def _map_imu_sensor_channels(self) -> dict[str, tuple[int, int, int]]:
        result: dict[str, tuple[int, int, int]] = {}
        expected_dimensions = (4, 3, 3)
        for sensor in self._imu_sensor_definitions:
            addresses: list[int] = []
            for name, expected_dimension in zip(
                imu_sensor_channel_names(sensor.id), expected_dimensions, strict=True
            ):
                sensor_index = self._mujoco.mj_name2id(
                    self.model,
                    self._mujoco.mjtObj.mjOBJ_SENSOR,
                    name,
                )
                if sensor_index < 0:
                    raise ValueError(f"MuJoCo IMU channel is missing: {name}")
                dimension = int(self.model.sensor_dim[sensor_index])
                if dimension != expected_dimension:
                    raise ValueError(
                        f"MuJoCo IMU channel {name} has dimension {dimension}; "
                        f"expected {expected_dimension}"
                    )
                addresses.append(int(self.model.sensor_adr[sensor_index]))
            result[sensor.id] = (addresses[0], addresses[1], addresses[2])
        return result

    def _imu_measurements(self) -> dict[str, ImuKinematics]:
        result: dict[str, ImuKinematics] = {}
        for sensor in self._imu_sensor_definitions:
            orientation_address, velocity_address, acceleration_address = (
                self._imu_channel_addresses[sensor.id]
            )
            w, x, y, z = (
                float(value)
                for value in self.data.sensordata[orientation_address : orientation_address + 4]
            )
            angular_velocity = self.data.sensordata[velocity_address : velocity_address + 3]
            linear_acceleration = self.data.sensordata[
                acceleration_address : acceleration_address + 3
            ]
            result[sensor.id] = ImuKinematics(
                orientation=(x, y, z, w),
                angular_velocity=(
                    float(angular_velocity[0]),
                    float(angular_velocity[1]),
                    float(angular_velocity[2]),
                ),
                linear_acceleration=(
                    float(linear_acceleration[0]),
                    float(linear_acceleration[1]),
                    float(linear_acceleration[2]),
                ),
            )
        return result

    def _map_rangefinder_sensor_channels(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for sensor in self._rangefinder_sensor_definitions:
            name = rangefinder_sensor_name(sensor.id)
            sensor_index = self._mujoco.mj_name2id(
                self.model,
                self._mujoco.mjtObj.mjOBJ_SENSOR,
                name,
            )
            if sensor_index < 0:
                raise ValueError(f"MuJoCo rangefinder channel is missing: {name}")
            dimension = int(self.model.sensor_dim[sensor_index])
            if dimension != 1:
                raise ValueError(
                    f"MuJoCo rangefinder channel {name} has dimension {dimension}; expected 1"
                )
            result[sensor.id] = int(self.model.sensor_adr[sensor_index])
        return result

    def _rangefinder_measurements(self) -> dict[str, RangefinderMeasurement]:
        result: dict[str, RangefinderMeasurement] = {}
        for sensor in self._rangefinder_sensor_definitions:
            if sensor.max_distance is None:
                raise ValueError(f"Rangefinder max_distance is missing: {sensor.id}")
            raw_distance = float(self.data.sensordata[self._rangefinder_addresses[sensor.id]])
            hit = 0.0 <= raw_distance <= sensor.max_distance
            result[sensor.id] = RangefinderMeasurement(
                distance=raw_distance if hit else sensor.max_distance,
                hit=hit,
            )
        return result

    def _apply_python_controller(self) -> None:
        if not self._controller_runner.enabled:
            return
        action = self._controller_runner.step(self._controller_observation())
        if action is not None:
            try:
                updates = self._validate_joint_position_targets(dict(action.position_targets))
                direct_updates = self._validate_actuator_controls(dict(action.actuator_controls))
                attachment_updates = self._validate_attachment_commands(
                    dict(action.attachment_commands)
                )
                mapped_ids = {identifier for identifier, _ in updates}
                duplicate_ids = mapped_ids & {identifier for identifier, _ in direct_updates}
                if duplicate_ids:
                    actuator_names = {
                        identifier: name for name, identifier in self._actuator_ids.items()
                    }
                    duplicate_names = sorted(
                        actuator_names[identifier] for identifier in duplicate_ids
                    )
                    raise ValueError(
                        "Controller action commands an actuator twice: "
                        + ", ".join(duplicate_names)
                    )
            except (TypeError, ValueError) as exc:
                self._controller_runner.fail(f"Controller action rejected: {exc}")
            else:
                self._apply_actuator_control_updates([*updates, *direct_updates])
                self._apply_attachment_command_updates(attachment_updates)
                if action.navigation is not None:
                    self._navigation_state = NavigationSimulationState.from_update(
                        action.navigation
                    )
        self._sync_python_controller_state()

    def _validate_quadrotor_bindings(self) -> None:
        for model in self._quadrotor_models:
            if model.body_link_id not in self._link_ids:
                raise ValueError(
                    f"Quadrotor {model.actor_id} body link was not exported to MuJoCo: "
                    f"{model.body_link_id}"
                )
            for rotor in model.rotors:
                if rotor.link_id not in self._link_ids:
                    raise ValueError(
                        f"Quadrotor rotor link was not exported to MuJoCo: {rotor.link_id}"
                    )
                if rotor.actuator_id not in self._actuator_ids:
                    raise ValueError(
                        f"Quadrotor actuator was not exported to MuJoCo: {rotor.actuator_id}"
                    )

    def _apply_quadrotor_forces(self) -> None:
        if not self._quadrotor_models:
            return
        affected_body_ids = {self._link_ids[model.body_link_id] for model in self._quadrotor_models}
        affected_body_ids.update(
            self._link_ids[rotor.link_id]
            for model in self._quadrotor_models
            for rotor in model.rotors
        )
        for body_id in affected_body_ids:
            self.data.xfrc_applied[body_id] = 0.0
        for model in self._quadrotor_models:
            body_id = self._link_ids[model.body_link_id]
            body_center = self.data.xipos[body_id]
            net_force = np.zeros(3, dtype=np.float64)
            net_torque = np.zeros(3, dtype=np.float64)
            for rotor in model.rotors:
                rotor_body_id = self._link_ids[rotor.link_id]
                actuator_id = self._actuator_ids[rotor.actuator_id]
                angular_velocity = float(self.data.ctrl[actuator_id])
                angular_velocity = max(
                    rotor.min_angular_velocity,
                    min(rotor.max_angular_velocity, angular_velocity),
                )
                squared_velocity = angular_velocity * angular_velocity
                rotation = self.data.xmat[rotor_body_id].reshape((3, 3))
                axis = rotation @ rotor.axis
                thrust = rotor.thrust_coefficient * squared_velocity
                reaction_torque = rotor.direction * rotor.torque_coefficient * squared_velocity
                force = axis * thrust
                lever = self.data.xpos[rotor_body_id] - body_center
                net_force += force
                net_torque += np.cross(lever, force)
                net_torque += axis * reaction_torque
            # The aerodynamic wrench belongs to the airframe. Applying reaction
            # torque directly to low-inertia, freely rotating visual rotor links
            # accelerates their hinges without bound and destabilizes MuJoCo.
            self.data.xfrc_applied[body_id, :3] += net_force
            self.data.xfrc_applied[body_id, 3:] += net_torque

    def _sync_python_controller_state(self) -> None:
        runner_state = self._controller_runner.state
        if runner_state.status == "fault":
            self._controller_status = "fault"
            self._controller_message = runner_state.message
        elif runner_state.status in {"ready", "active"}:
            self._controller_status = runner_state.status
            self._controller_message = None

    @staticmethod
    def _read_control_timeout(scene: Scene) -> float:
        value = float(scene.simulation_config.get("control_timeout", 0.0))
        if not math.isfinite(value) or value < 0:
            raise ValueError("simulation_config.control_timeout must be finite and >= 0")
        return value

    @staticmethod
    def _read_controller_deadline(scene: Scene) -> float | None:
        raw_value = scene.simulation_config.get("controller_deadline")
        if raw_value is None:
            return None
        value = float(raw_value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError("simulation_config.controller_deadline must be finite and > 0")
        return value

    @staticmethod
    def _read_controller_reset_deadline(scene: Scene) -> float | None:
        raw_value = scene.simulation_config.get("controller_reset_deadline")
        if raw_value is None:
            return None
        value = float(raw_value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(
                "simulation_config.controller_reset_deadline must be finite and > 0"
            )
        return value

    @staticmethod
    def _read_recording_max_samples(scene: Scene) -> int:
        raw_value = scene.simulation_config.get("recording_max_samples", 100_000)
        if isinstance(raw_value, bool):
            raise ValueError("simulation_config.recording_max_samples must be an integer >= 1")
        value = int(raw_value)
        if value < 1 or float(raw_value) != value:
            raise ValueError("simulation_config.recording_max_samples must be an integer >= 1")
        return value

    def _recording_state(self) -> RecordingSimulationState:
        recording = self._state_recorder.recording
        if recording is None:
            return RecordingSimulationState()
        return RecordingSimulationState(
            active=self._state_recorder.active,
            sample_count=len(recording.samples),
            sensor_event_count=sum(len(sample.sensors) for sample in recording.samples),
            limit_reached=recording.limit_reached,
            name=recording.name,
        )

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
