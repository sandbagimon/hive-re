# Quadrotor Propulsion and Control

SimLab models a quadrotor as four named velocity actuators plus an engine-neutral propulsion profile on
the Scene actor. Algorithms and controllers command rotor angular-velocity magnitudes in `rad/s`; only
the MuJoCo adapter converts those values to engine forces and moments.

## Dynamics contract

For rotor `i`, the quadratic model applies:

```text
thrust_i = k_f * omega_i^2
yaw_moment_i = direction_i * k_m * omega_i^2
```

The thrust and yaw moment follow the rotor's configured local axis, transformed into world coordinates
at every physics step. SimLab converts every rotor force into an equivalent force and `r × F` moment
about the airframe center of mass, adds the yaw reaction moment, and applies the summed wrench to the
main body. Visual rotor links therefore cannot destabilize physics through their small inertia.

The actor's `properties.propulsion` object owns all engine-independent parameters: body link, four rotor
link IDs, actuator IDs, local axes, yaw directions, coefficients, and angular-velocity bounds. Scene
validation rejects missing links/actuators, duplicate resources, invalid coefficients, or any rotor count
other than four.

The bundled Pegasus Iris profile uses:

- `k_f = 8.54858e-6 N/(rad/s)^2`
- `k_m = 1e-6 N·m/(rad/s)^2`
- rotor bounds `0..1100 rad/s`
- yaw directions `[-1, -1, 1, 1]`
- 1.5 kg body plus four 0.005 kg rotor links

The assembled center of mass and rotor mounts are slightly asymmetric. The bundled static hover trim is
`[641.132, 679.039, 646.467, 673.963] rad/s`; four equal `660 rad/s` commands have similar total thrust
but produce a non-zero roll/pitch moment. The trim holds an undisturbed initial pose, while a practical
flight controller still needs attitude and altitude feedback to reject disturbances.

## Python controller

Start the backend with trusted controller execution enabled, add the Pegasus Iris asset to the Scene,
then load [`examples/controllers/iris_hover.py`](../examples/controllers/iris_hover.py) from the
Controller panel. The example holds the static trim for a 0.5 second visual spool phase, follows a
two-second smooth one-meter takeoff profile, and uses altitude/vertical-velocity feedback to brake and
settle into hover. It emits all four values through `ControllerAction.actuator_controls` and does not
depend on MuJoCo objects.

For manual checks, selecting the Iris actor opens a Rotor Control section in the Inspector. Each rotor
has a bounded `rad/s` control, and **Stop Rotors** atomically returns all four commands to zero.

## REST control

The browser/manual control plane accepts stable actuator IDs:

```http
PUT /api/v1/simulations/{simulation_id}/actuator-controls
Content-Type: application/json

{
  "controls": {
    "actuator_iris_rotor_0": 641.132187,
    "actuator_iris_rotor_1": 679.039297,
    "actuator_iris_rotor_2": 646.466695,
    "actuator_iris_rotor_3": 673.962654
  }
}
```

Values are applied atomically, clamped to each actuator's declared range, published through the normal
simulation state event, and reset to Home with the rest of the session. The transport-neutral Bridge
method is `setActuatorControls`.

## Gymnasium and gRPC

`QuadrotorAdapter` maps a normalized four-value action in `[-1, 1]` to the declared actuator ranges and
returns a 13-value body observation (`xyz`, MuJoCo `wxyz` quaternion, world-frame linear velocity, and
world-frame angular velocity):

```python
from simlab.simulation import QuadrotorAdapter

robot = QuadrotorAdapter(
    [
        "actuator_iris_rotor_0",
        "actuator_iris_rotor_1",
        "actuator_iris_rotor_2",
        "actuator_iris_rotor_3",
    ],
    body_id="actor_001",
)
```

The adapter emits the existing dense `ControlCommand`, so local MuJoCo and remote gRPC sessions use the
same model description and action ordering. No quadrotor-only gRPC message is required.

## Current fidelity boundary

The first model includes quadratic thrust, rotor-position roll/pitch moments, quadratic yaw reaction
moments, and a frontend-only slowed rotor animation. It does not yet include physical motor spool
dynamics, propeller inflow, body drag, battery sag, ground effect, or wind. The example controller holds
altitude but does not yet reject horizontal or attitude disturbances. Those effects can be added behind
the same propulsion profile without changing REST, Controller, Gymnasium, or gRPC call sites.
