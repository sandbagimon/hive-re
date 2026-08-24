# Park Swarm Delivery (Multi-Drone Pickup & Delivery with Obstacle Avoidance)

## Goal

Ship a new example where three Iris quadcopters run simultaneous pickup-and-delivery
missions inside the streamed Architectural Brownstone Park (Full) scene, with live
obstacle avoidance (prior structures, two unmapped crossing vehicles, and
drone-to-drone deconfliction).

## Changes

- `src/beefoundrysim/controllers/iris_payload_delivery.py`: parameterized the base delivery
  controller (stable IDs, pickup/dropoff/home, cruise/hook heights incl. a separate
  `dropoff_hook_height`, payload mass) with defaults preserving the single-drone demo.
- `src/beefoundrysim/controllers/iris_obstacle_navigation.py` (new): parameterized
  `ObstacleDeliveryPilot` — the online navigation stack (rangefinder occupancy grid,
  incremental A* replanning, reactive repulsion/wall-following) previously duplicated
  in the examples obstacle controller. Adds `intruders` support (neighbouring airframes
  as transient map obstacles + repulsion) and a `minimum_hit_distance` self-reflection
  floor applied to both the occupancy grid and the reactive layer.
- `src/beefoundrysim/controllers/realtime_navigation.py`: `LiveOccupancyGrid.add_transient_obstacle`
  for intruder injection with TTL expiry.
- `examples/controllers/iris_obstacle_delivery.py`: thin subclass of the new core pilot;
  every public constant/helper re-exported so existing scenes/tests are unchanged.
- `examples/drone_delivery_park/` (new): scene builder — cloned Iris articulations with
  globally unique IDs per drone, per-drone rangefinders/attachments/payloads/tasks,
  terrain-aware pads and hook heights, prior obstacle map (park structures + kiosks),
  and two kinematic dynamic events parked outside the corridors.
- `examples/controllers/iris_swarm_delivery.py` (new): swarm wrapper running one pilot
  per airframe, merging actuator/attachment commands, injecting intruders, and
  aggregating navigation telemetry.
- `tests/test_drone_park_delivery.py` (new): ID uniqueness + validation, route-vs-prior
  obstacle checks, and a full end-to-end mission run asserting all three tasks complete
  with payloads on their dropoff pads.
- `docs/DRONE_PARK_SWARM_DELIVERY.md` (new): run instructions, architecture, and the
  engineering decisions below.

## Engineering decisions (found the hard way)

1. **MuJoCo collides meshes as convex hulls.** The full 192-box park OBJ as one mesh
   collider caps the workspace under an invisible shell (0.2–1.0 m above task points),
   lifting drones onto a phantom surface and blocking hook descents. Physics therefore
   uses an invisible floor slab plus explicit primitive colliders for the mission-relevant
   2.3 m structures; the viewport streams the park visually via `stream_scene_id`
   (which short-circuits primitive rendering).
2. **Multi-drone requires cloned articulations.** MJCF exports link IDs verbatim, the
   quadrotor propulsion layer claims rotor links/actuators exclusively, and attachments
   address bodies by ID — shared IDs across actors would alias to the first instance.
3. **Slung payloads self-reflect.** A swinging bag under the airframe (plus body tilt)
   can be swept by the vehicle's own horizontal rangefinders, seeding ghost obstacles
   that poison route checks and stall legs for minutes. Fixes: raise the ray mount to
   +0.22 m above the airframe centre and apply a 0.55 m minimum-hit floor in both the
   occupancy grid and the reactive avoidance layer.
4. **Idle dynamic obstacles must park outside corridors** — a permanently parked van on
   a planned route causes replan thrash. Similarly, prior obstacle layout must keep
   planned corridors ≥ ~2 m wide or reactive repulsion fights trajectory tracking in
   the pinch point.

## Validation

- `tests/test_drone_park_delivery.py`: 4/4 pass (full mission ≈ 100 s wall clock).
- Full backend suite: 311 passed, 3 skipped. ruff and mypy clean on touched modules.
