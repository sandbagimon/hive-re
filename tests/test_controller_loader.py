from __future__ import annotations

from pathlib import Path

import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.services.controller_loader import ControllerLoadError, ProjectControllerLoader
from simlab.services.controller_runtime import ControllerObservation
from simlab.services.openusd_importer import import_openusd_asset
from simlab.services.simulation_service import SimulationService


def _write_controller(path: Path, target: float = 0.5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from simlab.services.controller_runtime import ControllerAction\n"
        "class ProjectController:\n"
        "    name = 'Project Reach'\n"
        "    def reset(self, observation):\n"
        "        self.reset_time = observation.time\n"
        "    def step(self, observation):\n"
        f"        return ControllerAction({{'shoulder': {target!r}}})\n"
        "def create_controller():\n"
        "    return ProjectController()\n",
        encoding="utf-8",
    )


def test_project_controller_loader_loads_and_reloads_factory(tmp_path: Path) -> None:
    source = tmp_path / "controllers" / "reach.py"
    _write_controller(source, 0.25)
    loader = ProjectControllerLoader(tmp_path)

    first = loader.load(source)
    _write_controller(source, 0.75)
    second = loader.load(source)
    observation = ControllerObservation(time=0.0, timestep=0.01, joints={}, actuators={})
    first_action = first.controller.step(observation)
    second_action = second.controller.step(observation)

    assert first.name == "Project Reach"
    assert first.path == source.resolve()
    assert first_action is not None and first_action.position_targets["shoulder"] == 0.25
    assert second_action is not None and second_action.position_targets["shoulder"] == 0.75
    assert second.controller is not first.controller


def test_project_controller_loader_restricts_path_and_reports_import_phase(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside-controller.py"
    outside.write_text("def create_controller(): return None\n", encoding="utf-8")
    loader = ProjectControllerLoader(tmp_path)

    with pytest.raises(ControllerLoadError, match="inside project root") as path_error:
        loader.load(outside)
    assert path_error.value.phase == "path validation"

    invalid = tmp_path / "controllers" / "invalid.py"
    invalid.parent.mkdir(parents=True)
    invalid.write_text("def broken(:\n", encoding="utf-8")
    with pytest.raises(ControllerLoadError, match="import failed") as import_error:
        loader.load(invalid)
    assert import_error.value.phase == "import"
    assert import_error.value.traceback_text


def test_project_controller_loader_requires_factory_contract(tmp_path: Path) -> None:
    missing = tmp_path / "controllers" / "missing.py"
    missing.parent.mkdir(parents=True)
    missing.write_text("VALUE = 1\n", encoding="utf-8")
    invalid = tmp_path / "controllers" / "invalid.py"
    invalid.write_text("def create_controller(): return object()\n", encoding="utf-8")
    loader = ProjectControllerLoader(tmp_path)

    with pytest.raises(ControllerLoadError, match="create_controller"):
        loader.load(missing)
    with pytest.raises(ControllerLoadError, match=r"reset\(\) and step\(\)"):
        loader.load(invalid)


def test_project_controller_file_drives_external_openusd_robot(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    imported = import_openusd_asset(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda", tmp_path
    )
    articulation = imported.robotics_model.articulations[0]
    shoulder, elbow = articulation.joints
    source = tmp_path / "controllers" / "external_arm.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from simlab.services.controller_runtime import ControllerAction\n"
        "class ExternalArmController:\n"
        "    def reset(self, observation): pass\n"
        "    def step(self, observation):\n"
        f"        return ControllerAction({{{shoulder.id!r}: 0.6, {elbow.id!r}: -1.0}})\n"
        "def create_controller(): return ExternalArmController()\n",
        encoding="utf-8",
    )
    scene = Scene(
        actors=[
            Actor(
                id="actor_arm",
                name="Arm",
                type="robot",
                asset_id=imported.asset["id"],
                properties=imported.asset["default_properties"],
            )
        ],
        robotics=imported.robotics_model,
        simulation_config={"timestep": 0.01},
    )
    service = SimulationService(tmp_path, lambda _: None)

    attached, loaded = service.load_project_controller(scene, source)
    assert service.session is not None
    stepped = service.session.step(steps=100)

    assert loaded.name == "ExternalArmController"
    assert attached.controller.mode == "python"
    assert stepped.controller.step_count == 100
    assert [state.ctrl for state in stepped.actuators] == pytest.approx([0.6, -1.0])
    assert stepped.joints[0].qpos > 0.1
