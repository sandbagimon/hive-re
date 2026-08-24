# Third-Party Notices

This file records third-party components directly used or distributed by BeeFoundrySim. It is an inventory, not a replacement for the original license texts.

## OpenUSD / usd-core

- Source: <https://github.com/PixarAnimationStudios/OpenUSD>
- Package: `usd-core`
- Version policy: `>=25.5`; the current development environment uses 26.5.
- Purpose: read `.usd`, `.usda`, `.usdc`, and `.usdz` stages and standard `UsdPhysics` properties.
- License: TOST; consult <https://openusd.org/license> and the license included with the installed package.
- Distribution: dependency installed from the Python package index; not vendored in this repository.
- Replacement boundary: `src/beefoundrysim/services/openusd_importer.py`. A compatible USD reader can replace it without changing the Scene or Bridge schemas.

## three.js

- Source: <https://github.com/mrdoob/three.js>
- Vendored version: r160.
- Purpose: local editor viewport and transform controls.
- License: MIT; the vendored license is at `frontend/src/vendor/THREE_LICENSE.txt`.

## Mesh2Motion courier model and animations

- Source: <https://github.com/Mesh2Motion/mesh2motion-app>
- Files: `frontend/public/models/mesh2motion/courier/*.glb`.
- Purpose: skinned courier visual plus idle, walking, and seated riding-compatible glTF clips.
- License: CC0 1.0 Universal; provenance and file hashes are recorded in
  `frontend/public/models/mesh2motion/README.md`.

## Sketchfab Forklift Truck model

- Source: <https://sketchfab.com/3d-models/forklift-truck-060f3f8bc7de4e6ca2f348d414702e9d>
- Creator: louis-muir.
- File: `frontend/public/models/sketchfab/forklift/forklift.glb`.
- Purpose: textured forklift visual for the obstacle-aware delivery example.
- License: Creative Commons Attribution 4.0 International (`CC-BY-4.0`).
- Distribution: downloaded through the Objaverse 1.0 mirror; attribution, object ID,
  and file hash are recorded in `frontend/public/models/sketchfab/forklift/README.md`.

## Overture Maps and OpenStreetMap data

- Sources: <https://overturemaps.org/> and <https://www.openstreetmap.org/>.
- Purpose: building footprints, roads, and water surfaces for generated geospatial assets.
- License: the Overture Buildings theme and OpenStreetMap database are available under
  Open Data Commons Open Database License 1.0 (ODbL). Individual upstream sources may
  require additional attribution; consult the Overture attribution page and asset-local
  `SOURCE.md` before redistribution.
- Attribution used by the Shenzhen Houhai asset:
  `© OpenStreetMap contributors, Overture Maps Foundation`.
- Distribution: the repository contains only the selected source extract and generated
  LoD1 model, not the global datasets.
