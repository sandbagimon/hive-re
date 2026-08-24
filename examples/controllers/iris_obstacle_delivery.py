"""Obstacle-aware Iris delivery controller for the drone obstacle demo.

A thin, backwards-compatible wrapper around the shared
:class:`ObstacleDeliveryPilot` core: this module pins the single-drone demo's
identifiers, map bounds, and prior obstacles while the pilot itself owns the
online navigation stack (12-ray rangefinder occupancy grid, incremental A*
replanning, and reactive repulsion + wall following). Multi-drone scenes use
the core pilot directly, one instance per airframe.
"""

from __future__ import annotations

import math

from beefoundrysim.controllers.iris_obstacle_navigation import (
    ObstacleDeliveryPilot,
    plan_pilot_route,
)
from beefoundrysim.controllers.iris_payload_delivery import (
    ATTACHMENT_ID,
    CRUISE_HEIGHT,
    DROPOFF,
    HOOK_HEIGHT,
    IRIS_BODY_LINK,
    IRIS_ROTOR_ACTUATORS,
    PAYLOAD_BODY,
    PICKUP,
)
from beefoundrysim.controllers.realtime_navigation import GridSpec

# Rangefinders are mounted at even yaw angles on the Iris body; RAY_ANGLES is
# the beam direction in body frame, matched by index to the sensor IDs.
RAY_COUNT = 12
RAY_IDS = tuple(f"sensor_iris_range_{index:02d}" for index in range(RAY_COUNT))
RAY_ANGLES = tuple(2.0 * math.pi * index / RAY_COUNT for index in range(RAY_COUNT))

# Mission-map obstacles are rectangles (center_x, center_y, half_x, half_y).
# A* inflates them by the loaded vehicle/payload safety radius before planning.
MISSION_OBSTACLES = ((2.0, 1.5, 0.25, 0.8),)

# 2D navigation workspace: map bounds (min_x, max_x, min_y, max_y), grid cell
# size, and the safety radius kept around the vehicle (and its slung payload)
# when inflating obstacles.
MAP_BOUNDS = (-2.5, 5.0, -1.5, 4.0)
GRID_RESOLUTION = 0.2
LOADED_CLEARANCE = 0.68
GRID_SPEC = GridSpec(*MAP_BOUNDS, GRID_RESOLUTION)

# Scan geometry and cadence: beams originate 0.32 m from the body center, and
# the occupancy grid is refreshed every 40 ms of simulated time. The 25 Hz map
# rate is fast enough for the scene's pedestrians/vehicles while leaving the
# 100 Hz local avoidance loop responsive between grid updates.
RAY_ORIGIN_RADIUS = 0.32
MAP_UPDATE_PERIOD = 0.04
ROUTE_CHECK_PERIOD = 0.04

# Replanning budget and hysteresis: the A* planner spreads its node expansions
# across steps; replans are rate-limited and blocked routes are retried on a
# timer so a transient obstacle does not thrash the route.
PLANNER_EXPANSIONS_PER_STEP = 48
REPLAN_COOLDOWN = 0.25
REPLAN_RETRY_PERIOD = 0.5

# Progress watchdog: flying toward the goal must improve by MINIMUM_PROGRESS
# at least once per STALL_TIMEOUT, otherwise the route is assumed blocked.
STALL_TIMEOUT = 1.5
MINIMUM_PROGRESS = 0.12

# Ground clutter would poison the occupancy grid, so scans only count once the
# vehicle has climbed above this altitude.
MAPPING_MINIMUM_ALTITUDE = 0.75


def _point_blocked(
    point: tuple[float, float],
    obstacles: tuple[tuple[float, float, float, float], ...],
    clearance: float,
) -> bool:
    """Return True if ``point`` falls inside any rectangle inflated by ``clearance``."""
    x, y = point
    return any(
        abs(x - center_x) <= half_x + clearance
        and abs(y - center_y) <= half_y + clearance
        for center_x, center_y, half_x, half_y in obstacles
    )


def _segment_clear(
    start: tuple[float, float],
    end: tuple[float, float],
    obstacles: tuple[tuple[float, float, float, float], ...],
    clearance: float,
) -> bool:
    """Sample a segment at sub-cell spacing and check every point for collisions."""
    distance = math.hypot(end[0] - start[0], end[1] - start[1])
    sample_count = max(1, math.ceil(distance / (GRID_RESOLUTION * 0.45)))
    return all(
        not _point_blocked(
            (
                start[0] + (end[0] - start[0]) * index / sample_count,
                start[1] + (end[1] - start[1]) * index / sample_count,
            ),
            obstacles,
            clearance,
        )
        for index in range(sample_count + 1)
    )


def plan_route(
    start: tuple[float, float],
    goal: tuple[float, float],
    *,
    obstacles: tuple[tuple[float, float, float, float], ...] = MISSION_OBSTACLES,
    clearance: float = LOADED_CLEARANCE,
) -> tuple[tuple[float, float], ...]:
    """Plan and line-of-sight simplify an eight-connected occupancy-grid route."""
    return plan_pilot_route(
        GRID_SPEC, start, goal, obstacles=obstacles, clearance=clearance
    )


class IrisObstacleDeliveryController(ObstacleDeliveryPilot):
    """Online mapping and incremental replanning for physical payload delivery."""

    name = "Iris Obstacle-Aware Payload Delivery"

    def __init__(self) -> None:
        super().__init__(
            body_link_id=IRIS_BODY_LINK,
            payload_body_id=PAYLOAD_BODY,
            attachment_id=ATTACHMENT_ID,
            rotor_actuators=IRIS_ROTOR_ACTUATORS,
            pickup=PICKUP,
            dropoff=DROPOFF,
            home=(-2.0, 0.0),
            cruise_height=CRUISE_HEIGHT,
            hook_height=HOOK_HEIGHT,
            ray_ids=RAY_IDS,
            ray_angles=RAY_ANGLES,
            grid_spec=GRID_SPEC,
            prior_obstacles=MISSION_OBSTACLES,
            clearance=LOADED_CLEARANCE,
            ray_origin_radius=RAY_ORIGIN_RADIUS,
            map_update_period=MAP_UPDATE_PERIOD,
            route_check_period=ROUTE_CHECK_PERIOD,
            expansions_per_step=PLANNER_EXPANSIONS_PER_STEP,
            replan_cooldown=REPLAN_COOLDOWN,
            replan_retry_period=REPLAN_RETRY_PERIOD,
            stall_timeout=STALL_TIMEOUT,
            minimum_progress=MINIMUM_PROGRESS,
            mapping_minimum_altitude=MAPPING_MINIMUM_ALTITUDE,
        )


def create_controller() -> IrisObstacleDeliveryController:
    """Entry point used by the controller loader runtime."""
    return IrisObstacleDeliveryController()
