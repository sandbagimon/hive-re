from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import uvicorn

from beefoundrysim.web_server import create_app


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    data_root = Path(tempfile.mkdtemp(prefix="beefoundrysim-web-e2e-"))
    try:
        uvicorn.run(
            create_app(
                data_root,
                seed_assets=repository / "assets",
                cors_origins=["http://127.0.0.1:4173"],
                access_token="e2e-token",
                allow_controller_execution=True,
            ),
            host="127.0.0.1",
            port=8876,
        )
    finally:
        shutil.rmtree(data_root, ignore_errors=True)


if __name__ == "__main__":
    main()
