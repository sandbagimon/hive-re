#!/usr/bin/env python3
"""Download a PolyHaven GLTF asset at 2K resolution with all dependencies."""
import json
import sys
import urllib.request
from pathlib import Path

GLTF_BASE = "https://dl.polyhaven.org/file/ph-assets/Models/gltf/2k"
TEX_BASE = "https://dl.polyhaven.org/file/ph-assets/Models/jpg/2k"
DEST = Path("frontend/public/models/polyhaven")

def download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  skip (exists): {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading: {dest.name}")
    urllib.request.urlretrieve(url, dest)

def fetch_asset(asset_id: str) -> None:
    asset_dir = DEST / asset_id
    gltf_path = asset_dir / f"{asset_id}_2k.gltf"
    download(f"{GLTF_BASE}/{asset_id}/{asset_id}_2k.gltf", gltf_path)

    gltf = json.loads(gltf_path.read_text())
    # Download .bin (same gltf/2k path)
    for buffer in gltf.get("buffers", []):
        uri = buffer.get("uri", "")
        if uri.endswith(".bin"):
            download(f"{GLTF_BASE}/{asset_id}/{uri}", asset_dir / uri)

    # Download images from jpg/2k path, save to textures/ dir
    for image in gltf.get("images", []):
        uri = image.get("uri", "")
        if uri.startswith("textures/"):
            filename = uri.split("/")[-1]
            download(f"{TEX_BASE}/{asset_id}/{filename}", asset_dir / uri)

    print(f"  done: {asset_id}")

if __name__ == "__main__":
    assets = sys.argv[1:] or [
        "cardboard_box_01",
        "fire_hydrant",
        "plastic_crate_02",
        "jacaranda_tree",
        "wooden_crate_02",
    ]
    for a in assets:
        print(f"Fetching {a}...")
        try:
            fetch_asset(a)
        except Exception as exc:
            print(f"  ERROR: {exc}")
