# Primitive Geometry Contract

SimLab scene geometry uses meters, a right-handed Z-up world, and the following canonical rules.

## Primitive Size

- Box: `size = [half_x, half_y, half_z]`.
- Sphere: `size = [radius]`.
- Cylinder: `size = [radius, half_height]`, with its local axis along positive Z.
- Ellipsoid: `size = [radius_x, radius_y, radius_z]`.
- Plane: `size = [half_x, half_y, spacing]`. Its MuJoCo collision surface is infinite; finite ground assets should use a thin static Box.

All size values are positive and describe the unscaled authoring geometry.

## Transform

- Position is `[x, y, z]` in meters.
- Rotation is `[x, y, z]` Euler radians in three.js `XYZ` order.
- Scale is a positive `[x, y, z]` multiplier.
- MJCF export converts Euler rotation to a `w x y z` quaternion.
- MJCF export bakes scale into geom size; actor body transforms never carry scale.

## Scale Conversion

- Box: each half extent is multiplied by its matching scale component.
- Sphere: uniform scale remains a Sphere; non-uniform scale becomes an Ellipsoid.
- Cylinder: X/Y scale must match; it scales radius, while Z scales half-height.
- Plane: X/Y scale changes its rendered extent. Plane collision remains infinite.

Viewport geometry and MuJoCo collision geometry must both follow this contract. New primitive types require contract tests before being added to asset metadata.

The built-in Ground asset is a finite static Box centered below Z=0. Export never adds implicit collision geometry; every collider must be represented by a scene actor.
