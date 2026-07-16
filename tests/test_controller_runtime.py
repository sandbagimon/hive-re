from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from simlab.services.controller_runtime import (
    ActuatorObservation,
    ControllerAction,
    ControllerObservation,
    ControllerRunner,
    JointObservation,
)


def _observation(time: float = 0.0) -> ControllerObservation:
    return ControllerObservation(
        time=time,
        timestep=0.01,
        joints={"shoulder": JointObservation(qpos=0.1, qvel=-0.2)},
        actuators={"shoulder_drive": ActuatorObservation(ctrl=0.3, force=1.2)},
    )


def test_controller_observation_and_action_are_immutable() -> None:
    observation = _observation()
    action = ControllerAction({"shoulder": 0.5})

    with pytest.raises(TypeError):
        observation.joints["elbow"] = JointObservation(0.0, 0.0)  # type: ignore[index]
    with pytest.raises(TypeError):
        action.position_targets["shoulder"] = 0.0  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        observation.time = 1.0  # type: ignore[misc]


def test_controller_runner_calls_reset_and_step_with_stable_state() -> None:
    class HoldController:
        def __init__(self) -> None:
            self.reset_time: float | None = None

        def reset(self, observation: ControllerObservation) -> None:
            self.reset_time = observation.time

        def step(self, observation: ControllerObservation) -> ControllerAction:
            return ControllerAction({"shoulder": observation.joints["shoulder"].qpos + 0.1})

    controller = HoldController()
    runner = ControllerRunner()
    runner.attach(controller, name="Hold Shoulder")

    assert runner.reset(_observation()) is True
    action = runner.step(_observation(0.01))

    assert controller.reset_time == 0.0
    assert action is not None and action.position_targets == {"shoulder": 0.2}
    assert runner.state.status == "active"
    assert runner.state.name == "Hold Shoulder"
    assert runner.state.step_count == 1


def test_controller_runner_contains_exception_and_disables_future_steps() -> None:
    class FailingController:
        calls = 0

        def reset(self, observation: ControllerObservation) -> None:
            pass

        def step(self, observation: ControllerObservation) -> ControllerAction:
            self.calls += 1
            raise RuntimeError("control law diverged")

    controller = FailingController()
    runner = ControllerRunner()
    runner.attach(controller)

    assert runner.step(_observation()) is None
    assert runner.step(_observation(0.01)) is None
    assert controller.calls == 1
    assert runner.enabled is False
    assert runner.state.status == "fault"
    assert "control law diverged" in (runner.state.message or "")


def test_controller_runner_can_be_faulted_by_action_consumer() -> None:
    class Controller:
        def reset(self, observation: ControllerObservation) -> None:
            pass

        def step(self, observation: ControllerObservation) -> None:
            return None

    runner = ControllerRunner()
    runner.attach(Controller())

    runner.fail("Controller action rejected: unknown joint")

    assert runner.attached is True
    assert runner.enabled is False
    assert runner.state.status == "fault"
    assert "unknown joint" in (runner.state.message or "")


def test_controller_runner_disables_step_that_exceeds_deadline() -> None:
    values = iter([10.0, 10.025])

    class SlowController:
        def reset(self, observation: ControllerObservation) -> None:
            pass

        def step(self, observation: ControllerObservation) -> ControllerAction:
            return ControllerAction({"shoulder": 0.4})

    runner = ControllerRunner(deadline=0.01, clock=lambda: next(values))
    runner.attach(SlowController())

    assert runner.step(_observation()) is None
    assert runner.state.status == "fault"
    assert runner.state.last_duration == pytest.approx(0.025)
    assert "deadline exceeded" in (runner.state.message or "")


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_controller_contract_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        JointObservation(qpos=value, qvel=0.0)
    with pytest.raises(ValueError, match="finite"):
        ControllerAction({"shoulder": value})
