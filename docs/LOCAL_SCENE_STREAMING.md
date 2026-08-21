# Local Park scene streaming

The first local-scene vertical slice uses the Architectural Brownstone
`World_BrownstoneDemopack_Park(8Gb).usd` entry. The source pack remains outside project data:
the API opens it locally, creates a shared optimized cache, and streams spatial geometry chunks to
the browser. Three.js remains the renderer. MuJoCo receives a separate low-detail OBJ made from a
bounded set of static collision boxes.

## Start it

Unpack the asset pack so this file exists:

```text
external/architectural-brownstone/unpacked/Demos/AEC/BrownstoneDemo/World_BrownstoneDemopack_Park(8Gb).usd
```

The repository launcher discovers that default location automatically:

```bash
./start_backend.sh
./start_frontend.sh
```

For a different unpack location, point the backend at the pack root (not at the USD file):

```bash
SIMLAB_LOCAL_SCENE_ROOT=/absolute/path/to/unpacked ./start_backend.sh
```

The equivalent direct API command is:

```bash
.venv/bin/python -m simlab.web_server \
  --data-root .simlab-data \
  --seed-assets assets \
  --local-scene-root /absolute/path/to/unpacked
```

The first start prepares the cache in
`.simlab-data/local-scenes/brownstone-park-v3/` on a daemon worker. The asset browser polls while
that work is in progress and adds **Architectural Brownstone Park (8GB)** to the Environment group
when it is ready. Later starts reuse the cache while the entry file fingerprint is unchanged.

## Data path

```text
local OpenUSD pack
  -> backend stage traversal and meter/up-axis normalization
  -> 24 m spatial chunks, capped at 350k vertices each
  -> USD material inputs plus direct OmniPBR .mdl argument extraction
  -> geometry grouped by material plus allowlisted local PNG/JPG textures
  -> SIMGEOM1 binary buffers over authenticated HTTP
  -> Three.js progressive loading (3 concurrent requests) and frustum culling

selected roads / paths / structures
  -> at most 192 normalized AABB boxes
  -> per-project collision.obj
  -> existing MJCF / MuJoCo mesh collision path
```

The original 2.4 GB pack is neither uploaded to the browser nor copied into each project. Geometry
chunks and only the textures referenced by extracted browser-readable materials are copied into a
shared cache. Chunk and texture responses are immutable and browser-cacheable. The manifest,
chunk, and texture routes accept only the allowlisted `brownstone-park` scene and generated IDs;
clients cannot request arbitrary local paths.

## Current limits

- This is a static visual background; USD animation and runtime stage edits are intentionally not
  streamed.
- UsdPreviewSurface inputs and direct OmniPBR wrapper calls in local `.mdl` files are translated to
  Three.js materials, including base color, normal, ORM/AO, opacity, emissive parameters, and UV
  transforms. Unsupported procedural MDL graphs and missing resources use authored constants or a
  semantic color fallback; the backend does not execute arbitrary MDL code.
- Dense painted grass/flower/shrub layers remain excluded from the visual cache.
- Collision is deliberately approximate. Vegetation and sky geometry are excluded, while roads,
  paths, walls, buildings, street furniture, and similar structures become coarse boxes.
- A changed source entry invalidates the cache. Changes only inside a referenced dependency are not
  fingerprinted yet; remove the versioned cache directory or bump the cache version when developing
  dependency-level changes.
