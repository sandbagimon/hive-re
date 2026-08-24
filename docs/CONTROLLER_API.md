# Python Controller API

BeeFoundrySim controllers receive an immutable snapshot before every MuJoCo physics step and may return
joint position targets, named actuator controls, and attachment requests. They never receive mutable `MjModel` or
`MjData` objects.

```python
from beefoundrysim.services.controller_runtime import (
    ControllerAction,
    ControllerObservation,
)


class ReachController:
    def reset(self, observation: ControllerObservation) -> None:
        self.started_at = observation.time

    def step(self, observation: ControllerObservation) -> ControllerAction:
        shoulder = observation.joints["joint_shoulder"]
        target = min(0.6, shoulder.qpos + 0.01)
        return ControllerAction({"joint_shoulder": target})


session.attach_controller(ReachController(), name="Reach")
state = session.step(steps=100)
session.detach_controller()
```

`ControllerObservation` contains simulation `time`, fixed `timestep`, joint `qpos/qvel`, actuator
`ctrl/force`, body pose/linear/angular velocity, and attachment eligibility/contact/distance/speed,
all keyed by stable Scene IDs.
`ControllerAction.position_targets` addresses
position-driven joints, `ControllerAction.actuator_controls` addresses actuators directly, and
`ControllerAction.attachment_commands` requests attachment activation or release. Session validates all
maps atomically and applies the same stable-ID lookup and range clamping used by REST and UI commands.
One action cannot address the same actuator through both actuator maps.

Controllers may optionally return a typed `NavigationUpdate` in `ControllerAction.navigation`. The
session publishes its route, navigation/map revisions, status, replan count, occupied-cell count, last
replan time, and message as `SimulationState.navigation`. This telemetry does not mutate the authoring
scene and is delivered to browser clients through the existing simulation WebSocket.

For example, a quadrotor controller can command rotor angular velocities without importing MuJoCo:

```python
return ControllerAction(
    actuator_controls={
        "actuator_iris_rotor_0": 641.132187,
        "actuator_iris_rotor_1": 679.039297,
        "actuator_iris_rotor_2": 646.466695,
        "actuator_iris_rotor_3": 673.962654,
    }
)
```

The complete loadable example is
[`examples/controllers/iris_hover.py`](../examples/controllers/iris_hover.py).
The physical pickup-and-delivery example at
[`examples/controllers/iris_payload_delivery.py`](../examples/controllers/iris_payload_delivery.py)
also demonstrates contact-gated attachment commands; see
[`DRONE_DELIVERY.md`](DRONE_DELIVERY.md).

For a reusable bounded outer loop, import `JointPdConfig` and `JointPositionPdController` from
`beefoundrysim.controllers`. It computes a qpos/qvel correction, limits each per-step position-target delta, and
leaves force generation to the MuJoCo position actuator. Runtime goals can be changed with `set_target()`
or atomic `set_targets()`. See [`examples/controllers/two_joint_pd.py`](../examples/controllers/two_joint_pd.py)
for a project-loadable example that configures the first two observed joints relative to Home without
hard-coded USD Prim names.

Controller lifecycle:

- `attach_controller()` calls `reset()` once at the current simulation state.
- `step()` runs before each `mj_step`.
- Session `reset()` invokes `reset()` again for a healthy attached controller.
- Exceptions, invalid actions, and configured deadline overruns set controller status to `fault` and
  disable later callbacks. Physics stepping continues.
- `detach_controller()` is required before manual joint commands or trajectory playback.

Set `simulation_config.controller_deadline` to a positive number of seconds to enforce a per-step
deadline. Controller `reset()` is initialization work and has a separate optional
`simulation_config.controller_reset_deadline`; when it is omitted, reset duration is not limited. These
are elapsed-time checks, not thread preemption: an overrun is detected after the user callback returns,
its action is discarded, and later callbacks are disabled.

Project controller files define a no-argument factory:

```python
def create_controller():
    return ReachController()
```

`ProjectControllerLoader` only accepts `.py` files whose resolved path is inside the project root. Loading
is always explicit, recompiles the source for reload, and reports path validation, import, factory, or
contract validation as distinct phases. Scene Open never executes controller code. The Python Bridge
provides `loadController`, `loadControllerPath`, and `detachController`. The robot Inspector Controller
section exposes explicit Load, Reload, and Detach controls; Load and Reload require trusted-code confirmation.

Controller modules are trusted in-process Python code with the same filesystem permissions as BeeFoundrySim. The
project-root check prevents accidental selection outside the project, but it is not a security sandbox.
