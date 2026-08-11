# Cinematic delivery texture

`wet-asphalt-albedo.png` is a project-local base-color texture generated with OpenAI's built-in
image generation tool on 2026-08-10. It is used only by the three.js visual layer; MuJoCo keeps a
simple box collider for the road.

- Dimensions: 1254 × 1254 RGB PNG
- SHA-256: `6bfc76775fce3551a7bc95026859697b5ce88aff475317ed793dab39fd2bf593`
- Intended use: repeating wet asphalt base color under procedural roughness/bump and clearcoat
- Limit: this is an albedo-style source, not a measured multi-channel PBR scan

The generation brief requested a tileable, orthographic, evenly exposed blue-hour wet-asphalt
material without markings, objects, perspective, text, shadows, or baked illumination.
