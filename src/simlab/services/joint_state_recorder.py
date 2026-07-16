from __future__ import annotations

import math
from typing import TYPE_CHECKING

from simlab.models.recording import (
    ActuatorRecordingState,
    JointRecordingState,
    JointStateRecording,
    JointStateSample,
    RecordingManifest,
)

if TYPE_CHECKING:
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
        timestep: float,
        scene_version: str,
        engine_version: str,
    ) -> JointStateRecording:
        if self.active:
            raise RuntimeError("Joint state recording is already active")
        if not name.strip():
            raise ValueError("Recording name cannot be empty")
        if not joint_ids and not actuator_ids:
            raise ValueError("Recording must select at least one joint or actuator")
        if len(joint_ids) != len(set(joint_ids)):
            raise ValueError("Recording joint IDs must be unique")
        if len(actuator_ids) != len(set(actuator_ids)):
            raise ValueError("Recording actuator IDs must be unique")
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
        )
        self.active = True
        return self.recording

    def capture(self, state: SimulationState) -> bool:
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
        )
        values = [sample.time]
        values.extend(value for item in sample.joints.values() for value in (item.qpos, item.qvel))
        values.extend(
            value for item in sample.actuators.values() for value in (item.ctrl, item.force)
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Recording sample values must be finite")
        recording.samples.append(sample)
        return True

    def stop(self) -> JointStateRecording:
        recording = self._require_recording()
        self.active = False
        return recording

    def _require_recording(self) -> JointStateRecording:
        if self.recording is None:
            raise RuntimeError("No joint state recording has been started")
        return self.recording
