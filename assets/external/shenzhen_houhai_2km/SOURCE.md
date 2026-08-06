# Shenzhen Houhai 2 km × 2 km

- Center (WGS84): `113.919790, 22.526595`
- Extent: approximately `2,000 m × 2,000 m`
- Buildings: Overture Maps Foundation, Buildings theme
- Roads and water: OpenStreetMap Overpass API
- Snapshot: `2026-07-22.0`
- Access date: `2026-08-03`
- Attribution: `© OpenStreetMap contributors, Overture Maps Foundation`
- Buildings license: Open Data Commons Open Database License 1.0 (ODbL)

`houhai_2km.usdc` is an LoD1 visualization/simulation model generated from building
footprints. Authored heights and floor counts are preserved when present. Missing heights
use a documented footprint-area heuristic, so this asset is not survey-grade and must not
be used for navigation or safety-critical digital-twin decisions.

## Visual style

The generated stage uses the deterministic **Houhai daylight** palette. Buildings are
bucketed by semantic type and height into 13 bounded wall/roof styles, while arterial,
collector, local, and pedestrian roads use separate display colors. Major-road center lines
and water are visual-only; ground and building shells remain the dedicated MuJoCo collision
geometry. The browser activates its daylight sky, color management, and large-environment
lighting when this kilometre-scale asset is present.

Rebuild after downloading the release spatial index:

```bash
.venv/bin/pip install -e '.[geospatial]'

curl -fL \
  https://stac.overturemaps.org/2026-07-22.0/collections.parquet \
  -o assets/external/shenzhen_houhai_2km/source/collections-2026-07-22.0.parquet

curl -fL --data-binary \
  @assets/external/shenzhen_houhai_2km/source/osm-overpass.ql \
  https://overpass.kumi.systems/api/interpreter \
  -o assets/external/shenzhen_houhai_2km/source/osm-roads-water.json

.venv/bin/python scripts/build_houhai_usd.py
```
