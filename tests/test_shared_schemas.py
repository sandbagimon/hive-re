import json
from pathlib import Path

from jsonschema import Draft202012Validator


def test_shared_scene_physics_robotics_and_bridge_schemas_are_declared() -> None:
    root = Path("shared/schemas")
    scene = json.loads((root / "scene.schema.json").read_text(encoding="utf-8"))
    physics = json.loads((root / "physics.schema.json").read_text(encoding="utf-8"))
    bridge = json.loads((root / "bridge-protocol.schema.json").read_text(encoding="utf-8"))
    robotics = json.loads((root / "robotics.schema.json").read_text(encoding="utf-8"))
    trajectory = json.loads(
        (root / "joint-trajectory.schema.json").read_text(encoding="utf-8")
    )
    recording = json.loads(
        (root / "joint-recording.schema.json").read_text(encoding="utf-8")
    )

    assert scene["title"] == "SimLabScene"
    assert "physics" in scene["$defs"]["actor"]["properties"]["properties"]["properties"]
    assert {"rubber", "wood", "metal", "ice"}.issubset(
        physics["properties"]["material"]["enum"]
    )
    assert "runSimulation" in bridge["properties"]["rpc_methods"]["const"]
    assert "importOpenUsd" in bridge["properties"]["rpc_methods"]["const"]
    assert "importOpenUsdPath" in bridge["properties"]["rpc_methods"]["const"]
    assert "openProjectPath" in bridge["properties"]["rpc_methods"]["const"]
    assert "saveProjectPath" in bridge["properties"]["rpc_methods"]["const"]
    assert "getVisualGeometry" in bridge["properties"]["rpc_methods"]["const"]
    assert "setJointTargets" in bridge["properties"]["rpc_methods"]["const"]
    assert "setActuatorControls" in bridge["properties"]["rpc_methods"]["const"]
    assert "setAttachmentCommands" in bridge["properties"]["rpc_methods"]["const"]
    assert "loadTrajectory" in bridge["properties"]["rpc_methods"]["const"]
    assert "playTrajectory" in bridge["properties"]["rpc_methods"]["const"]
    assert "simulationStateChanged" in bridge["properties"]["events"]["const"]
    simulation_state = bridge["$defs"]["simulationState"]
    assert {
        "links",
        "joints",
        "actuators",
        "attachments",
        "delivery_tasks",
        "sensors",
        "controller",
        "trajectory",
        "recording",
    }.issubset(
        simulation_state["required"]
    )
    assert scene["$defs"]["attachment"]["properties"]["type"]["enum"] == [
        "connect",
        "weld",
    ]
    assert (
        scene["$defs"]["vacuumGripper"]["properties"]["type"]["const"]
        == "four_cup_vacuum"
    )
    assert (
        scene["$defs"]["deliveryTask"]["properties"]["type"]["const"]
        == "aerial_delivery"
    )
    sensor_variants = simulation_state["properties"]["sensors"]["items"]["oneOf"]
    assert {
        variant["properties"]["sensor_type"]["const"] for variant in sensor_variants
    } == {"joint_state", "imu", "contact", "rangefinder"}
    assert "startRecording" in bridge["properties"]["rpc_methods"]["const"]
    assert "exportRecording" in bridge["properties"]["rpc_methods"]["const"]
    assert "exportRecordingDialog" in bridge["properties"]["rpc_methods"]["const"]
    assert "meshGeometry" in scene["$defs"]
    assert {"quadrotorRotor", "quadrotorPropulsion"}.issubset(scene["$defs"])
    assert scene["properties"]["robotics"]["$ref"] == "robotics.schema.json"
    assert scene["properties"]["trajectories"]["items"]["$ref"] == (
        "#/$defs/trajectoryClip"
    )
    assert scene["$defs"]["trajectoryClip"]["properties"]["trajectory"]["$ref"] == (
        "joint-trajectory.schema.json"
    )
    assert robotics["title"] == "SimLabRoboticsModel"
    assert trajectory["title"] == "SimLabJointTrajectory"
    assert recording["title"] == "SimLabJointStateRecording"
    assert recording["properties"]["manifest"]["properties"]["engine"] == {
        "type": "string",
        "minLength": 1,
    }
    solver_contract = scene["properties"]["simulation_config"]["properties"]["solvers"]
    assert solver_contract["oneOf"][1]["properties"]["extensions"]["uniqueItems"]
    assert {
        "sensorState",
        "jointSensorState",
        "imuSensorState",
        "contactSensorState",
        "rangefinderSensorState",
    }.issubset(
        recording["$defs"]
    )
    assert "sensor_ids" in recording["required"]
    assert "sensor_types" in recording["required"]
    assert set(
        recording["properties"]["sensor_types"]["additionalProperties"]["enum"]
    ) == {"joint_state", "imu", "contact", "rangefinder"}
    assert trajectory["properties"]["keyframes"]["minItems"] == 2
    assert {"link", "joint", "actuator", "sensor", "collider", "inertial"}.issubset(
        robotics["$defs"]
    )
    assert "local_transform" in robotics["$defs"]["sensor"]["properties"]
    assert "collider_id" in robotics["$defs"]["sensor"]["properties"]
    assert "aggregation_mode" in robotics["$defs"]["sensor"]["properties"]
    assert "max_distance" in robotics["$defs"]["sensor"]["properties"]
    assert "noise" in robotics["$defs"]["sensor"]["properties"]
    assert {"sensorNoise", "scalarNoiseChannel", "vectorNoiseChannel"}.issubset(
        robotics["$defs"]
    )
    Draft202012Validator.check_schema(robotics)
    Draft202012Validator.check_schema(bridge)
    Draft202012Validator.check_schema(trajectory)
    Draft202012Validator.check_schema(recording)
