import csv
import io

import pytest

from simlab.models.recording import JointStateRecording
from simlab.services.joint_state_recorder import JointStateRecorder
from simlab.services.simulation_session import (
    ActuatorSimulationState,
    JointSimulationState,
    SimulationState,
)


def _state(time: float, *, qpos: float = 0.0) -> SimulationState:
    return SimulationState(
        time=time,
        actors=[],
        joints=[
            JointSimulationState("shoulder", qpos, 0.25),
            JointSimulationState("elbow", -0.4, -0.1),
        ],
        actuators=[
            ActuatorSimulationState("shoulder_drive", 0.5, 2.0),
            ActuatorSimulationState("elbow_drive", -0.4, -1.0),
        ],
    )


def _recorder(max_samples: int = 100) -> JointStateRecorder:
    recorder = JointStateRecorder(max_samples=max_samples)
    recorder.start(
        name="Arm Run",
        joint_ids=["shoulder"],
        actuator_ids=["shoulder_drive"],
        timestep=0.01,
        scene_version="1.0",
        engine_version="3.3.7",
    )
    return recorder


def test_joint_state_recording_round_trip_and_csv() -> None:
    recorder = _recorder()

    assert recorder.capture(_state(0.0)) is True
    assert recorder.capture(_state(0.01, qpos=0.1)) is True
    recording = recorder.stop()
    restored = JointStateRecording.from_dict(recording.to_dict())
    rows = list(csv.reader(io.StringIO(restored.to_csv())))

    assert restored.to_dict() == recording.to_dict()
    assert restored.manifest.engine == "mujoco"
    assert rows[0] == [
        "time",
        "joint.shoulder.qpos",
        "joint.shoulder.qvel",
        "actuator.shoulder_drive.ctrl",
        "actuator.shoulder_drive.force",
    ]
    assert [float(value) for value in rows[-1]] == [0.01, 0.1, 0.25, 0.5, 2.0]


def test_joint_state_recorder_stops_at_sample_limit() -> None:
    recorder = _recorder(max_samples=2)
    recorder.capture(_state(0.0))
    recorder.capture(_state(0.01))

    assert recorder.capture(_state(0.02)) is False
    assert recorder.active is False
    assert recorder.recording is not None
    assert recorder.recording.limit_reached is True
    assert len(recorder.recording.samples) == 2


def test_joint_state_recorder_rejects_missing_id() -> None:
    recorder = JointStateRecorder()
    recorder.start(
        name="Missing",
        joint_ids=["wrist"],
        actuator_ids=[],
        timestep=0.01,
        scene_version="1.0",
        engine_version="3.3.7",
    )

    with pytest.raises(ValueError, match="missing selected ID"):
        recorder.capture(_state(0.0))


def test_joint_state_recorder_rejects_non_increasing_time() -> None:
    recorder = _recorder()
    recorder.capture(_state(0.01))

    with pytest.raises(ValueError, match="strictly increasing"):
        recorder.capture(_state(0.01))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "", "joint_ids": ["shoulder"], "actuator_ids": []},
        {"name": "Empty", "joint_ids": [], "actuator_ids": []},
        {
            "name": "Duplicate",
            "joint_ids": ["shoulder", "shoulder"],
            "actuator_ids": [],
        },
    ],
)
def test_joint_state_recorder_rejects_invalid_selection(kwargs: dict) -> None:
    recorder = JointStateRecorder()

    with pytest.raises(ValueError):
        recorder.start(
            **kwargs,
            timestep=0.01,
            scene_version="1.0",
            engine_version="3.3.7",
        )
