# Nested PointInstancer Composition

## Problem

The **Architectural Brownstone Park (Full)** local scene rendered a lone tree (plus a
small hydrangea clump) roughly 55 m east of the park boundary, near the world origin.
The Optimized variant did not show it.

## Root Cause

The NVIDIA Brownstone stage authors painted vegetation as **nested PointInstancers**:
an outer scatter instancer (e.g. `/PaintTool/Douglas_Fir_33ccc/pointInstancer`, 263
painted trees) whose prototype `asset` Xform contains a trunk mesh plus inner
PointInstancers (branch/flower scatter with per-tree offsets). The stage is authored in
centimeter units with the park around x ≈ -11000 cm; the prototype subtree itself sits
near the world origin.

The previous expansion logic in `_geometry_instances` and
`_full_point_instance_groups` treated every PointInstancer prim independently:

1. Inner instancers were traversed at top level and expanded at their **authored stage
   location** (near the origin), producing the stray tree outside the park.
2. Inner-instancer prototype meshes leaked into the outer prototype walk without the
   inner instance transforms, so per-tree branch scatter collapsed onto single offsets.
3. The Optimized variant masked the bug because `_visual_path_allowed` filters
   `/painttool/` paths; `_full_visual_path_allowed` keeps them by design.

## Fix

- `src/beefoundrysim/services/openusd/mesh_extractor.py`: new `_PointInstancerCopies`
  iterator. It identifies root instancers (those not inside another instancer's
  prototype subtree), memoizes per-instancer transforms and per-prototype parts, prunes
  nested instancer subtrees from direct geometry parts, and recursively composes
  nested copies as `relative * innerInstance * nestedRelative * outerInstance *
  base`. Cyclic nesting is skipped with a warning. `_geometry_instances` now consumes
  it, so optimized baking and the general OpenUSD import path are fixed too.
- `src/beefoundrysim/services/local_scene_streaming.py`: `_full_point_instance_groups`
  consumes the same iterator, preserving composed copies as GPU instance matrices
  grouped by `(root instancer, prototype child path)`.
- `FULL_CACHE_VERSION` bumped 2 → 3 so stale full caches rebuild automatically.
- `tests/test_local_scene_streaming.py`: regression fixtures with a nested
  scatter→asset→branch-instancer hierarchy assert exact composed translations for both
  profiles and that no copy remains at the authored prototype location.

## Validation

- `tests/test_local_scene_streaming.py` (7 tests) and the OpenUSD importer suites pass.
- Rebuilding the real full cache moves all formerly origin-collapsed chunks into park
  tiles; no instanced geometry remains east of the park bounds.
