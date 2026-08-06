# Third-Party Notices

This file records third-party components directly used or distributed by SimLab. It is an inventory, not a replacement for the original license texts.

## OpenUSD / usd-core

- Source: <https://github.com/PixarAnimationStudios/OpenUSD>
- Package: `usd-core`
- Version policy: `>=25.5`; the current development environment uses 26.5.
- Purpose: read `.usd`, `.usda`, `.usdc`, and `.usdz` stages and standard `UsdPhysics` properties.
- License: TOST; consult <https://openusd.org/license> and the license included with the installed package.
- Distribution: dependency installed from the Python package index; not vendored in this repository.
- Replacement boundary: `src/simlab/services/openusd_importer.py`. A compatible USD reader can replace it without changing the Scene or Bridge schemas.

## three.js

- Source: <https://github.com/mrdoob/three.js>
- Vendored version: r160.
- Purpose: local editor viewport and transform controls.
- License: MIT; the vendored license is at `frontend/src/vendor/THREE_LICENSE.txt`.

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
