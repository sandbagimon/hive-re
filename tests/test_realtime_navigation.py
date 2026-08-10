from __future__ import annotations

from examples.controllers.iris_obstacle_delivery import (
    ATTACHMENT_ID,
    CRUISE_HEIGHT,
    DROPOFF,
    GRID_SPEC,
    IRIS_BODY_LINK,
    IRIS_ROTOR_ACTUATORS,
    RAY_IDS,
    IrisObstacleDeliveryController,
)
from simlab.controllers.realtime_navigation import (
    GridSpec,
    IncrementalAStarPlanner,
    LiveOccupancyGrid,
    route_is_clear,
)
from simlab.services.controller_runtime import (
    ActuatorObservation,
    AttachmentObservation,
    BodyObservation,
    ControllerObservation,
    RangefinderObservation,
)


def test_live_scan_invalidates_route_and_incremental_astar_routes_around_hit() -> None:
    spec = GridSpec(-1.0, 5.0, -2.0, 2.0, 0.2)
    occupancy = LiveOccupancyGrid(spec, clearance=0.55)
    occupancy.update_scan(
        body_position=(0.0, 0.0),
        yaw=0.0,
        beams=((0.0, 2.0, 4.0, True),),
        now=0.0,
    )
    blocked = occupancy.blocked_cells()

    assert not route_is_clear(((0.0, 0.0), (4.0, 0.0)), spec, blocked)
    planner = IncrementalAStarPlanner(spec, (0.0, 0.0), (4.0, 0.0), blocked)
    assert planner.advance(1) == "planning"
    while planner.advance(8) == "planning":
        pass

    assert planner.status == "ready"
    assert planner.route is not None
    assert len(planner.route) >= 3
    assert route_is_clear(planner.route, spec, blocked)
    assert planner.expansion_count > 1


def test_observed_obstacle_expires_when_no_longer_seen() -> None:
    spec = GridSpec(-1.0, 5.0, -2.0, 2.0, 0.2)
    occupancy = LiveOccupancyGrid(spec, clearance=0.55, observation_ttl=1.0)
    occupancy.update_scan(
        body_position=(0.0, 0.0),
        yaw=0.0,
        beams=((0.0, 2.0, 4.0, True),),
        now=0.0,
    )
    revision = occupancy.revision

    changed = occupancy.update_scan(
        body_position=(0.0, 0.0),
        yaw=0.0,
        beams=(),
        now=1.01,
    )

    assert changed is True
    assert occupancy.observed_cell_count == 0
    assert occupancy.revision == revision + 1


def test_drone_controller_replans_online_from_live_range_scan() -> None:
    controller = IrisObstacleDeliveryController()
    controller.reset(_observation(0.0))
    controller.route = ((0.0, 0.0), DROPOFF)
    controller.route_index = 1
    controller.phase = "navigate_loaded_1"
    controller.phase_started_at = 0.0
    controller.segment_start = (0.0, 0.0, CRUISE_HEIGHT)
    controller.segment_target = (*DROPOFF, CRUISE_HEIGHT)
    controller.segment_duration = 100.0
    controller.hold_payload = True
    controller.navigation_status = "following"

    updates = []
    for index in range(200):
        action = controller.step(_observation(index * 0.002, hit_sensor=1))
        if action.navigation is not None:
            updates.append(action.navigation)
        if controller.replan_count:
            break

    assert controller.replan_count == 1
    assert controller.route_revision == 2
    assert controller.navigation_status == "following"
    assert controller.planner is None
    assert route_is_clear(
        controller.route,
        GRID_SPEC,
        controller.occupancy.blocked_cells(),
    )
    assert any(update.status == "planning" for update in updates)
    assert updates[-1].status == "following"


def _observation(
    time: float,
    *,
    hit_sensor: int | None = None,
) -> ControllerObservation:
    ranges = {
        sensor_id: RangefinderObservation(
            distance=1.2 if index == hit_sensor else 4.0,
            max_distance=4.0,
            hit=index == hit_sensor,
        )
        for index, sensor_id in enumerate(RAY_IDS)
    }
    body = BodyObservation(
        position=(0.0, 0.0, CRUISE_HEIGHT),
        quaternion=(1.0, 0.0, 0.0, 0.0),
        linear_velocity=(0.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
    )
    return ControllerObservation(
        time=time,
        timestep=0.002,
        joints={},
        actuators={
            actuator_id: ActuatorObservation(ctrl=0.0, force=0.0)
            for actuator_id in IRIS_ROTOR_ACTUATORS
        },
        bodies={
            IRIS_BODY_LINK: body,
            "actor_003": BodyObservation(
                position=(0.0, 0.0, 0.16),
                quaternion=(1.0, 0.0, 0.0, 0.0),
                linear_velocity=(0.0, 0.0, 0.0),
                angular_velocity=(0.0, 0.0, 0.0),
            ),
        },
        attachments={
            ATTACHMENT_ID: AttachmentObservation(
                active=True,
                requested_active=True,
                eligible=False,
                contact=False,
                distance=0.0,
                relative_speed=0.0,
            )
        },
        rangefinders=ranges,
    )
