from __future__ import annotations

import math
from typing import TYPE_CHECKING

from simlab.models.recording import (
    ActuatorRecordingState,
    ContactRecordingState,
    ImuRecordingState,
    JointRecordingState,
    JointStateRecording,
    JointStateSample,
    RecordingManifest,
    SensorRecordingState,
    TypedSensorRecordingState,
)
from simlab.services.contact_sensors import ContactSensorSample
from simlab.services.imu_sensors import ImuSensorSample
from simlab.services.joint_state_sensors import JointStateSensorSample

if TYPE_CHECKING:
    from collections.abc import Sequence

    from simlab.services.simulation_session import SimulationState


class JointStateRecorder:
    """Bounded physics-state recorder keyed by stable robotics IDs."""

    def __init__(self, max_samples: int = 100_000) -> None:
        if max_samples <= 0:
            raise ValueError("Recording max_samples must be greater than zero")
        self.max_samples = max_samples
        self.recording: JointStateRecording | None = None
        self.active = False

    def start(
        self,
        *,
        name: str,
        joint_ids: list[str],
        actuator_ids: list[str],
        sensor_ids: list[str] | None = None,
        sensor_types: dict[str, str] | None = None,
        timestep: float,
        scene_version: str,
        engine_version: str,
    ) -> JointStateRecording:
        if self.active:
            raise RuntimeError("Joint state recording is already active")
        if not name.strip():
            raise ValueError("Recording name cannot be empty")
        selected_sensor_ids = sensor_ids or []
        if not joint_ids and not actuator_ids and not selected_sensor_ids:
            raise ValueError("Recording must select at least one joint, actuator, or sensor")
        if len(joint_ids) != len(set(joint_ids)):
            raise ValueError("Recording joint IDs must be unique")
        if len(actuator_ids) != len(set(actuator_ids)):
            raise ValueError("Recording actuator IDs must be unique")
        if len(selected_sensor_ids) != len(set(selected_sensor_ids)):
            raise ValueError("Recording sensor IDs must be unique")
        selected_sensor_types = (
            {sensor_id: "joint_state" for sensor_id in selected_sensor_ids}
            if sensor_types is None
            else dict(sensor_types)
        )
        if set(selected_sensor_types) != set(selected_sensor_ids):
            raise ValueError("Recording sensor_types keys must match sensor_ids")
        if any(
            sensor_type not in {"joint_state", "imu", "contact"}
            for sensor_type in selected_sensor_types.values()
        ):
            raise ValueError(
                "Recording sensor type must be 'joint_state', 'imu', or 'contact'"
            )
        if not math.isfinite(timestep) or timestep <= 0:
            raise ValueError("Recording timestep must be finite and greater than zero")
        self.recording = JointStateRecording(
            name=name.strip(),
            manifest=RecordingManifest(
                engine_version=engine_version,
                timestep=timestep,
                scene_version=scene_version,
            ),
            joint_ids=list(joint_ids),
            actuator_ids=list(actuator_ids),
            sensor_ids=list(selected_sensor_ids),
            sensor_types=selected_sensor_types,  # type: ignore[arg-type]
        )
        self.active = True
        return self.recording

    def capture(
        self,
        state: SimulationState,
        emitted_sensors: Sequence[
            JointStateSensorSample | ImuSensorSample | ContactSensorSample
        ] = (),
    ) -> bool:
        recording = self._require_recording()
        if not self.active:
            return False
        if len(recording.samples) >= self.max_samples:
            recording.limit_reached = True
            self.active = False
            return False
        if recording.samples and state.time <= recording.samples[-1].time:
            raise ValueError("Recording sample time must be strictly increasing")
        joints = {item.joint_id: item for item in state.joints}
        actuators = {item.actuator_id: item for item in state.actuators}
        missing_joints = [item for item in recording.joint_ids if item not in joints]
        missing_actuators = [item for item in recording.actuator_ids if item not in actuators]
        if missing_joints or missing_actuators:
            missing = ", ".join(missing_joints + missing_actuators)
            raise ValueError(f"Recording state is missing selected ID(s): {missing}")
        sample = JointStateSample(
            time=float(state.time),
            joints={
                joint_id: JointRecordingState(
                    qpos=float(joints[joint_id].qpos),
                    qvel=float(joints[joint_id].qvel),
                )
                for joint_id in recording.joint_ids
            },
            actuators={
                actuator_id: ActuatorRecordingState(
                    ctrl=float(actuators[actuator_id].ctrl),
                    force=float(actuators[actuator_id].force),
                )
                for actuator_id in recording.actuator_ids
            },
            sensors={
                sensor.sensor_id: self._record_sensor(sensor)
                for sensor in emitted_sensors
                if sensor.sensor_id in recording.sensor_ids
            },
        )
        values = [sample.time]
        values.extend(value for item in sample.joints.values() for value in (item.qpos, item.qvel))
        values.extend(
            value for item in sample.actuators.values() for value in (item.ctrl, item.force)
        )
        for item in sample.sensors.values():
            if isinstance(item, SensorRecordingState):
                values.extend((item.time, item.qpos, item.qvel))
            elif isinstance(item, ImuRecordingState):
                values.extend(
                    (
                        item.time,
                        *item.orientation,
                        *item.angular_velocity,
                        *item.linear_acceleration,
                    )
                )
            else:
                values.extend(
                    (
                        item.time,
                        item.normal_force,
                        item.normal_impulse,
                        *item.tangent_force,
                        *(value for point in item.points for value in point),
                        *(value for normal in item.normals for value in normal),
                    )
                )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Recording sample values must be finite")
        recording.samples.append(sample)
        return True

    @staticmethod
    def _record_sensor(
        sensor: JointStateSensorSample | ImuSensorSample | ContactSensorSample,
    ) -> TypedSensorRecordingState:
        if isinstance(sensor, ContactSensorSample):
            return ContactRecordingState(
                time=float(sensor.time),
                sequence=int(sensor.sequence),
                contact_count=sensor.measurement.contact_count,
                normal_force=sensor.measurement.normal_force,
                normal_impulse=sensor.measurement.normal_impulse,
                tangent_force=sensor.measurement.tangent_force,
                points=sensor.measurement.points,
                normals=sensor.measurement.normals,
            )
        if isinstance(sensor, ImuSensorSample):
            return ImuRecordingState(
                link_id=sensor.link_id,
                time=float(sensor.time),
                sequence=int(sensor.sequence),
                orientation=sensor.orientation,
                angular_velocity=sensor.angular_velocity,
                linear_acceleration=sensor.linear_acceleration,
            )
        return SensorRecordingState(
            joint_id=sensor.joint_id,
            time=float(sensor.time),
            sequence=int(sensor.sequence),
            qpos=float(sensor.qpos),
            qvel=float(sensor.qvel),
        )

    def stop(self) -> JointStateRecording:
        recording = self._require_recording()
        self.active = False
        return recording

    def _require_recording(self) -> JointStateRecording:
        if self.recording is None:
            raise RuntimeError("No joint state recording has been started")
        return self.recording
