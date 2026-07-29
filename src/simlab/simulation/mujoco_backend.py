from __future__ import annotations

import tempfile
from pathlib import Path
from typing import cast

from simlab.models.robotics import Actuator, Joint
from simlab.services.simulation_session import MuJoCoSimulationSession, SimulationState
from simlab.simulation.backend import (
    ActuatorDescription,
    BackendSessionClosedError,
    BackendState,
    BodyDescription,
    ControlCommand,
    InvalidControlError,
    JointDescription,
    ModelDescription,
    ModelSchemaMismatchError,
    ResetOptions,
    SceneBundle,
    SimulationBackendError,
    model_schema_hash,
    validate_state_layout,
)


class MujocoBackend:
    """Factory for isolated, deterministic in-process MuJoCo sessions."""

    def create_session(self, bundle: SceneBundle) -> MujocoBackendSession:
        return MujocoBackendSession(bundle)


class MujocoBackendSession:
    """The only algorithm-side layer allowed to know MuJoCo runtime details."""

    def __init__(self, bundle: SceneBundle) -> None:
        scene = bundle.scene()
        self._temporary_directory: tempfile.TemporaryDirectory[str] | None = None
        if bundle.export_path is None:
            self._temporary_directory = tempfile.TemporaryDirectory(prefix="simlab-env-")
            export_path = Path(self._temporary_directory.name) / "scene.xml"
        else:
            export_path = Path(bundle.export_path)
        self._session: MuJoCoSimulationSession | None = MuJoCoSimulationSession(
            scene,
            export_path,
            asset_root=bundle.asset_root,
        )
        self._step_index = 0
        self._description = self._build_description(bundle.scene_hash)

    @property
    def model_description(self) -> ModelDescription:
        return self._description

    def reset(
        self,
        *,
        seed: int | None = None,
        options: ResetOptions | None = None,
    ) -> BackendState:
        del seed  # MuJoCo itself is deterministic; task randomization owns the RNG.
        session = self._require_open()
        session.reset()
        self._step_index = 0
        if options is not None:
            self._apply_reset_options(options)
        return self._snapshot(session.state())

    def step(self, command: ControlCommand, *, physics_steps: int = 1) -> BackendState:
        session = self._require_open()
        if isinstance(physics_steps, bool) or physics_steps < 1:
            raise ValueError("physics_steps must be an integer >= 1")
        if command.schema_hash != self._description.schema_hash:
            raise ModelSchemaMismatchError(
                "Control command model schema does not match the simulation session"
            )
        if len(command.values) != len(self._description.actuators):
            raise InvalidControlError(
                f"Expected {len(self._description.actuators)} actuator controls; "
                f"received {len(command.values)}"
            )
        for value, actuator in zip(command.values, self._description.actuators, strict=True):
            if value < actuator.lower or value > actuator.upper:
                raise InvalidControlError(
                    f"Control for {actuator.id} must be in [{actuator.lower}, {actuator.upper}]"
                )
        for value, actuator in zip(command.values, self._description.actuators, strict=True):
            session.data.ctrl[session._actuator_ids[actuator.id]] = value
        state = session.step(physics_steps)
        self._step_index += physics_steps
        return self._snapshot(state)

    def close(self) -> None:
        self._session = None
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()
            self._temporary_directory = None

    def _require_open(self) -> MuJoCoSimulationSession:
        if self._session is None:
            raise BackendSessionClosedError("Simulation session is closed")
        return self._session

    def _build_description(self, scene_hash: str) -> ModelDescription:
        session = self._require_open()
        state = session.state()
        body_ids = [item.actor_id for item in state.actors]
        body_ids.extend(item.actor_id for item in state.links if item.actor_id not in body_ids)
        joint_definitions: dict[str, Joint] = {}
        actuator_definitions: dict[str, Actuator] = {}
        robotics = session.scene.robotics
        if robotics is not None:
            joint_definitions = {
                joint.id: joint
                for articulation in robotics.articulations
                for joint in articulation.joints
            }
            actuator_definitions = {
                actuator.id: actuator
                for articulation in robotics.articulations
                for actuator in articulation.actuators
            }
        joints = tuple(
            JointDescription(
                id=item.joint_id,
                lower=_joint_bound(joint_definitions.get(item.joint_id), "lower"),
                upper=_joint_bound(joint_definitions.get(item.joint_id), "upper"),
            )
            for item in state.joints
        )
        actuators = tuple(
            ActuatorDescription(
                id=item.actuator_id,
                joint_id=actuator_definitions[item.actuator_id].joint_id,
                control_type=actuator_definitions[item.actuator_id].control_type,
                lower=actuator_definitions[item.actuator_id].control_range[0],
                upper=actuator_definitions[item.actuator_id].control_range[1],
            )
            for item in state.actuators
            if item.actuator_id in actuator_definitions
        )
        if len(actuators) != len(state.actuators):
            raise SimulationBackendError(
                "MuJoCo actuator layout does not match the canonical robotics model"
            )
        schema_hash = model_schema_hash(
            body_ids=body_ids,
            joint_ids=[item.id for item in joints],
            actuator_ids=[item.id for item in actuators],
        )
        return ModelDescription(
            backend_name="mujoco-local",
            backend_version=str(session._mujoco.__version__),
            timestep=float(session.model.opt.timestep),
            scene_hash=scene_hash,
            schema_hash=schema_hash,
            bodies=tuple(BodyDescription(id=identifier) for identifier in body_ids),
            joints=joints,
            actuators=actuators,
        )

    def _apply_reset_options(self, options: ResetOptions) -> None:
        session = self._require_open()
        for values, mapping, address_field, label in (
            (options.joint_positions, session._joint_ids, session.model.jnt_qposadr, "joint"),
            (options.joint_velocities, session._joint_ids, session.model.jnt_dofadr, "joint"),
        ):
            unknown = sorted(set(values) - set(mapping))
            if unknown:
                raise SimulationBackendError(
                    f"Reset references unknown {label} ID(s): {', '.join(unknown)}"
                )
            target = session.data.qpos if values is options.joint_positions else session.data.qvel
            for identifier, value in values.items():
                target[address_field[mapping[identifier]]] = value
        unknown_actuators = sorted(set(options.actuator_controls) - set(session._actuator_ids))
        if unknown_actuators:
            raise SimulationBackendError(
                "Reset references unknown actuator ID(s): " + ", ".join(unknown_actuators)
            )
        actuator_descriptions = {item.id: item for item in self._description.actuators}
        for identifier, value in options.actuator_controls.items():
            actuator = actuator_descriptions[identifier]
            if value < actuator.lower or value > actuator.upper:
                raise InvalidControlError(
                    f"Control for {identifier} must be in [{actuator.lower}, {actuator.upper}]"
                )
            session.data.ctrl[session._actuator_ids[identifier]] = value
        session._mujoco.mj_forward(session.model, session.data)
        session._reset_sensors()

    def _snapshot(self, state: SimulationState) -> BackendState:
        description = self._description
        joint_by_id = {item.joint_id: item for item in state.joints}
        actuator_by_id = {item.actuator_id: item for item in state.actuators}
        body_by_id = {item.actor_id: item for item in [*state.actors, *state.links]}
        return validate_state_layout(
            description,
            BackendState(
                schema_hash=description.schema_hash,
                time=state.time,
                step_index=self._step_index,
                joint_positions=tuple(joint_by_id[item.id].qpos for item in description.joints),
                joint_velocities=tuple(joint_by_id[item.id].qvel for item in description.joints),
                actuator_controls=tuple(
                    actuator_by_id[item.id].ctrl for item in description.actuators
                ),
                actuator_forces=tuple(
                    actuator_by_id[item.id].force for item in description.actuators
                ),
                body_positions=tuple(
                    cast(
                        tuple[float, float, float],
                        tuple(body_by_id[item.id].position),
                    )
                    for item in description.bodies
                ),
                body_quaternions=tuple(
                    cast(
                        tuple[float, float, float, float],
                        tuple(body_by_id[item.id].quaternion),
                    )
                    for item in description.bodies
                ),
            ),
        )


def _joint_bound(joint: Joint | None, field_name: str) -> float | None:
    if joint is None or joint.limits is None:
        return None
    return getattr(joint.limits, field_name)
