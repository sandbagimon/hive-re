from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def openusd_asset_id(path: Path) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_") or "asset"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:10]
    return f"openusd_{cleaned}_{digest}"


def upsert_asset_metadata(path: Path, asset: dict[str, Any]) -> None:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"assets": []}
    assets = data.setdefault("assets", [])
    assets[:] = [item for item in assets if item.get("id") != asset["id"]]
    assets.append(asset)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
