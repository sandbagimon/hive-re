from __future__ import annotations

import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.models.transform import Transform
from simlab.services.simulation_service import SimulationService


class FakeClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _scene(timestep: float = 0.01, max_catch_up_steps: int = 8) -> Scene:
    return Scene(
        name="Fixed Clock",
        actors=[
            Actor(
                id="actor_box",
                name="Box",
                type="object",
                asset_id="primitive_box",
                transform=Transform(position=[0.0, 0.0, 1.0]),
                properties={"primitive": "box", "size": [0.1, 0.1, 0.1]},
            )
        ],
        simulation_config={
            "timestep": timestep,
            "max_catch_up_steps": max_catch_up_steps,
        },
    )


def test_simulation_clock_accumulates_wall_time_into_fixed_steps(tmp_path) -> None:
    pytest.importorskip("mujoco")
    clock = FakeClock()
    service = SimulationService(tmp_path, lambda _: None, clock=clock)
    service.start(_scene())

    clock.advance(0.016)
    first = service.step_frame()
    clock.advance(0.016)
    second = service.step_frame()
    clock.advance(0.001)
    third = service.step_frame()

    assert first is not None and first.time == pytest.approx(0.01)
    assert second is not None and second.time == pytest.approx(0.03)
    assert third is not None and third.time == pytest.approx(0.03)


def test_simulation_clock_caps_catch_up_and_discards_pause_gap(tmp_path) -> None:
    pytest.importorskip("mujoco")
    clock = FakeClock()
    scene = _scene(max_catch_up_steps=4)
    service = SimulationService(tmp_path, lambda _: None, clock=clock)
    service.start(scene)

    clock.advance(1.0)
    caught_up = service.step_frame()
    service.pause()
    clock.advance(10.0)
    resumed = service.start(scene)
    clock.advance(0.01)
    after_resume = service.step_frame()

    assert caught_up is not None and caught_up.time == pytest.approx(0.04)
    assert resumed.time == pytest.approx(0.04)
    assert after_resume is not None and after_resume.time == pytest.approx(0.05)


@pytest.mark.parametrize("value", [0, -1, 1.5, True])
def test_simulation_clock_rejects_invalid_catch_up_limit(tmp_path, value) -> None:
    pytest.importorskip("mujoco")
    clock = FakeClock()
    scene = _scene()
    scene.simulation_config["max_catch_up_steps"] = value
    service = SimulationService(tmp_path, lambda _: None, clock=clock)

    with pytest.raises(ValueError, match="max_catch_up_steps"):
        service.start(scene)


def test_simulation_clock_stops_after_runtime_step_failure(tmp_path) -> None:
    pytest.importorskip("mujoco")
    clock = FakeClock()
    service = SimulationService(tmp_path, lambda _: None, clock=clock)
    service.start(_scene())
    assert service.session is not None

    def fail_step(steps: int = 1):
        raise RuntimeError(f"step failed after request for {steps}")

    service.session.step = fail_step
    clock.advance(0.01)

    with pytest.raises(RuntimeError, match="step failed"):
        service.step_frame()

    assert service.running is False
    assert service.step_frame() is None


def test_simulation_reset_preserves_loaded_session_and_returns_home(tmp_path) -> None:
    pytest.importorskip("mujoco")
    clock = FakeClock()
    scene = _scene()
    service = SimulationService(tmp_path, lambda _: None, clock=clock)
    service.start(scene)
    loaded_session = service.session
    clock.advance(0.02)
    service.step_frame()

    reset = service.reset()

    assert reset is not None and reset.time == 0.0
    assert service.session is loaded_session
    assert service.running is False
    assert service.step_frame() is None

    service.stop()
    assert service.session is None
