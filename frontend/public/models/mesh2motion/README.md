# Mesh2Motion courier visual and locomotion clips

These browser-ready GLB assets replace the courier's procedural capsule in the
`drone_delivery_obstacles` example. They are visual-only: the simplified box remains the
authoritative MuJoCo collision body.

Both files are distributed by the Mesh2Motion project under the
[CC0 1.0 Universal license](https://creativecommons.org/publicdomain/zero/1.0/). The project
states that its 3D models, rigs, and animations are CC0 in
[`LICENSE-CC0.MD`](https://github.com/Mesh2Motion/mesh2motion-app/blob/main/LICENSE-CC0.MD).

## Courier character

- File: `courier/human-jay.glb`
- Source: <https://github.com/Mesh2Motion/mesh2motion-app/blob/main/static/models-variation/human-jay.glb>
- Author: Mesh2Motion contributors
- SHA-256: `f3dbb7dc81d31d1d95acc0684932d9cc28022a002612accfaa8192e2d4a38e24`

## Human animation library

- File: `courier/human-base-animations.glb`
- Source: <https://github.com/Mesh2Motion/mesh2motion-app/blob/main/static/animations/human-base-animations.glb>
- Authors: Quaternius and Mesh2Motion contributors
- Used clips: `Idle_A`, `Walk`; the scene schema also maps cycling mode to the seated
  `Driving` clip supplied by the same library.
- SHA-256: `406eb0a8dc4ab366e623b79b6e3005a4951392e1bda78ae39c1099d31147733c`

The downloaded GLBs are unmodified. Scene-specific fitting, the courier pack, clip selection,
idle/locomotion blending, and simulation-speed synchronization are applied at runtime.
