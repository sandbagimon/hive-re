from __future__ import annotations

import pytest

from simlab.models.robotics import Articulation, Collider, Link, RoboticsModel, Sensor
from simlab.services.mujoco_contact_adapter import MujocoContactAggregator


def _robotics(scope: str = "collider") -> RoboticsModel:
    link = Link(
        id="link_box",
        name="Box",
        colliders=[Collider("collider_box", "Box", "box", size=[0.1, 0.1, 0.1])],
    )
    sensor = Sensor(
        id="sensor_contact",
        name="Box Contact",
        sensor_type="contact",
        link_id=link.id if scope == "link" else None,
        collider_id="collider_box" if scope == "collider" else None,
        aggregation_mode="sum",
        update_rate_hz=100.0,
    )
    return RoboticsModel(
        articulations=[
            Articulation(
                id="box_robot",
                name="Box Robot",
                root_link_id=link.id,
                fixed_base=False,
                links=[link],
                sensors=[sensor],
            )
        ]
    )


def _model_and_data():
    mujoco = pytest.importorskip("mujoco")
    model = mujoco.MjModel.from_xml_string(
        """
        <mujoco>
          <option timestep="0.01" gravity="0 0 -9.81"/>
          <worldbody>
            <geom name="ground" type="plane" size="2 2 0.1"/>
            <body name="box" pos="0 0 0.11">
              <freejoint/>
              <geom name="collider_box" type="box" size="0.1 0.1 0.1" mass="1"/>
            </body>
          </worldbody>
        </mujoco>
        """
    )
    data = mujoco.MjData(model)
    return mujoco, model, data


@pytest.mark.parametrize("scope", ["collider", "link"])
def test_mujoco_contact_adapter_aggregates_scoped_ground_contact(scope: str) -> None:
    mujoco, model, data = _model_and_data()
    adapter = MujocoContactAggregator(mujoco, model, data, _robotics(scope), 0.01)

    empty = adapter.measurements()["sensor_contact"]
    for _ in range(80):
        mujoco.mj_step(model, data)
    active = adapter.measurements()["sensor_contact"]

    assert empty.contact_count == 0
    assert active.contact_count >= 1
    assert active.normal_force == pytest.approx(9.81, rel=0.1)
    assert active.normal_impulse == pytest.approx(0.0981, rel=0.1)
    assert active.tangent_force == pytest.approx((0.0, 0.0, 0.0), abs=1e-5)
    assert active.points[0][2] == pytest.approx(0.0, abs=0.002)
    assert active.normals[0] == pytest.approx((0.0, 0.0, -1.0), abs=1e-6)


def test_mujoco_contact_adapter_rejects_missing_geom_mapping() -> None:
    mujoco, model, data = _model_and_data()
    robotics = _robotics()
    robotics.articulations[0].links[0].colliders[0].id = "collider_missing"
    robotics.articulations[0].sensors[0].collider_id = "collider_missing"

    with pytest.raises(ValueError, match="MuJoCo contact geom is missing"):
        MujocoContactAggregator(mujoco, model, data, robotics, 0.01)


def test_mujoco_contact_adapter_reports_tangent_force_on_scoped_geom() -> None:
    mujoco, model, data = _model_and_data()
    adapter = MujocoContactAggregator(mujoco, model, data, _robotics(), 0.01)
    for _ in range(80):
        mujoco.mj_step(model, data)

    data.qvel[0] = 1.0
    mujoco.mj_step(model, data)
    measurement = adapter.measurements()["sensor_contact"]

    assert measurement.contact_count >= 1
    assert measurement.tangent_force[0] < 0
