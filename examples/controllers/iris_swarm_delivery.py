"""Swarm delivery controller for the Brownstone Park multi-drone demo.

Runs one :class:`ObstacleDeliveryPilot` per airframe — each with its own
cloned-articulation IDs, 12-ray rangefinder set, prior park map, and pickup /
dropoff leg — and merges their actions into a single ControllerAction. The
pilots deconflict with each other twice: neighbouring airframes are injected
into every pilot's live occupancy grid (so A* routes around them) and repelled
by the reactive avoidance layer. Navigation telemetry is aggregated for the
frontend Navigation panel.
"""

from __future__ import annotations

import math

from beefoundrysim.controllers.iris_obstacle_navigation import ObstacleDeliveryPilot
from beefoundrysim.controllers.realtime_navigation import GridSpec
from beefoundrysim.services.controller_runtime import (
    ControllerAction,
    ControllerObservation,
    NavigationUpdate,
)

# Cloned-articulation identifiers from examples/drone_delivery_park/scene.py.
IRIS_BODY_LINK = "link_c46480014a33"
ROTOR_ACTUATORS = tuple(f"actuator_iris_rotor_{index}" for index in range(4))

RAY_COUNT = 12
RAY_ANGLES = tuple(2.0 * math.pi * index / RAY_COUNT for index in range(RAY_COUNT))

MAP_BOUNDS = (-108.0, -86.0, -14.0, 13.0)
GRID_RESOLUTION = 0.25
LOADED_CLEARANCE = 0.68
GRID_SPEC = GridSpec(*MAP_BOUNDS, GRID_RESOLUTION)

CRUISE_HEIGHT = 1.6
HOOK_HEIGHT = 0.39

# Prior obstacles: the park's two 2.3 m structures plus the two kiosks.
# Corridor widths are tuned against the scene so A* never plans a leg
# hugging an obstacle closer than ~2 m.
PRIOR_OBSTACLES = (
    (-96.7, 1.55, 1.35, 1.4),
    (-95.8, 3.55, 1.35, 1.4),
    (-99.0, -4.5, 0.8, 0.8),
    (-91.5, 6.5, 0.8, 0.8),
)

# (codename, home, pickup, dropoff, pickup hook height, dropoff hook height)
# mirrored from the scene's terrain-aware pad placement.
MISSIONS = (
    (
        "alpha",
        (-106.5, -6.0),
        (-103.5, -6.0),
        (-89.5, 3.0),
        0.05 + HOOK_HEIGHT,
        0.32 + HOOK_HEIGHT,
    ),
    (
        "bravo",
        (-106.5, 6.0),
        (-103.5, 6.0),
        (-89.5, -6.0),
        0.30 + HOOK_HEIGHT,
        0.60 + HOOK_HEIGHT,
    ),
    (
        "charlie",
        (-95.5, -12.0),
        (-95.5, -10.0),
        (-95.5, 10.5),
        0.75 + HOOK_HEIGHT,
        0.00 + HOOK_HEIGHT,
    ),
)


def _pilot(codename: str, home, pickup, dropoff, pickup_hook, dropoff_hook):
    return ObstacleDeliveryPilot(
        body_link_id=f"{IRIS_BODY_LINK}_{codename}",
        payload_body_id=f"actor_payload_{codename}",
        attachment_id=f"attachment_iris_hook_{codename}",
        rotor_actuators=tuple(
            f"{actuator}_{codename}" for actuator in ROTOR_ACTUATORS
        ),
        pickup=pickup,
        dropoff=dropoff,
        home=home,
        cruise_height=CRUISE_HEIGHT,
        hook_height=pickup_hook,
        dropoff_hook_height=dropoff_hook,
        ray_ids=tuple(
            f"sensor_iris_range_{index:02d}_{codename}" for index in range(RAY_COUNT)
        ),
        ray_angles=RAY_ANGLES,
        grid_spec=GRID_SPEC,
        prior_obstacles=PRIOR_OBSTACLES,
        clearance=LOADED_CLEARANCE,
        # The slung bag swings ~0.4 m under each airframe; ignoring near hits
        # keeps it out of the occupancy grid as a self-reflection ghost.
        minimum_hit_distance=0.55,
    )


_STATUS_PRIORITY = (
    "blocked",
    "planning",
    "ready",
    "following",
    "arrived",
    "complete",
)


class IrisSwarmDeliveryController:
    """Three simultaneous obstacle-aware pickup-and-delivery missions."""

    name = "Iris Park Swarm Delivery"

    def __init__(self) -> None:
        self.pilots = {
            codename: _pilot(codename, home, pickup, dropoff, pickup_hook, dropoff_hook)
            for codename, home, pickup, dropoff, pickup_hook, dropoff_hook in MISSIONS
        }
        self.telemetry_dirty = True

    def reset(self, observation: ControllerObservation) -> None:
        for pilot in self.pilots.values():
            pilot.reset(observation)
        self.telemetry_dirty = True

    def step(self, observation: ControllerObservation) -> ControllerAction:
        actuator_controls: dict[str, float] = {}
        attachment_commands: dict[str, bool] = {}
        navigation = None
        for codename, pilot in self.pilots.items():
            # Every other airframe is a transient map obstacle + repulsion
            # source for this pilot, giving drone-to-drone deconfliction.
            intruders = tuple(
                (
                    observation.bodies[other.body_link_id].position[0],
                    observation.bodies[other.body_link_id].position[1],
                )
                for name, other in self.pilots.items()
                if name != codename and other.body_link_id in observation.bodies
            )
            action = pilot.step(observation, intruders)
            actuator_controls.update(action.actuator_controls)
            attachment_commands.update(action.attachment_commands)
            if action.navigation is not None:
                self.telemetry_dirty = True
        if self.telemetry_dirty:
            navigation = self._navigation_update()
            self.telemetry_dirty = False
        return ControllerAction(
            actuator_controls=actuator_controls,
            attachment_commands=attachment_commands,
            navigation=navigation,
        )

    def _navigation_update(self) -> NavigationUpdate:
        """Aggregate per-pilot telemetry into one Navigation panel update."""
        statuses = {
            codename: pilot.navigation_status
            for codename, pilot in self.pilots.items()
        }
        active = next(
            (
                (codename, pilot)
                for codename, pilot in self.pilots.items()
                if pilot.navigation_status != "complete"
            ),
            None,
        )
        worst = "complete"
        for status in statuses.values():
            if _STATUS_PRIORITY.index(status) < _STATUS_PRIORITY.index(worst):
                worst = status
        pilot = self.pilots[active[0]] if active else next(iter(self.pilots.values()))
        return NavigationUpdate(
            status=worst,
            route=tuple((x, y, CRUISE_HEIGHT) for x, y in pilot.route),
            route_revision=pilot.route_revision,
            map_revision=max(
                p.occupancy.revision for p in self.pilots.values()
            ),
            replan_count=sum(p.replan_count for p in self.pilots.values()),
            occupied_cell_count=sum(
                p.occupancy.observed_cell_count for p in self.pilots.values()
            ),
            last_replan_time=max(
                (
                    p.last_replan_time
                    for p in self.pilots.values()
                    if p.last_replan_time is not None
                ),
                default=None,
            ),
            message=", ".join(
                f"{codename}:{status}" for codename, status in statuses.items()
            ),
        )


def create_controller() -> IrisSwarmDeliveryController:
    """Entry point used by the controller loader runtime."""
    return IrisSwarmDeliveryController()
