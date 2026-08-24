from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from beefoundrysim.api_v1 import create_v1_router
from beefoundrysim.resources import ResourceManager

DEFAULT_CORS_ORIGINS = [
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def create_app(
    data_root: Path | None = None,
    *,
    seed_assets: Path | None = None,
    cors_origins: list[str] | None = None,
    access_token: str | None = None,
    allow_controller_execution: bool = False,
    local_scene_root: Path | None = None,
) -> FastAPI:
    root = (data_root or repository_root() / ".beefoundrysim-data").resolve()
    assets = (seed_assets or repository_root() / "assets").resolve()
    manager = ResourceManager(
        root,
        assets,
        allow_controller_execution=allow_controller_execution,
        local_scene_root=local_scene_root,
    )
    app = FastAPI(
        title="BeeFoundrySim API",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
        swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
    )
    app.state.resources = manager
    app.state.access_token = access_token
    app.add_event_handler("shutdown", manager.close)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or DEFAULT_CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "If-None-Match"],
        expose_headers=[
            "Cache-Control",
            "Content-Disposition",
            "ETag",
            "X-BeeFoundrySim-Artifact-Id",
        ],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    app.include_router(create_v1_router(manager, access_token))

    @app.exception_handler(KeyError)
    async def missing_resource(_request: Request, exc: KeyError) -> JSONResponse:
        return error_response(404, str(exc).strip("'"))

    @app.exception_handler(PermissionError)
    async def permission_error(_request: Request, exc: PermissionError) -> JSONResponse:
        return error_response(403, str(exc))

    @app.exception_handler(ValueError)
    async def invalid_request(_request: Request, exc: ValueError) -> JSONResponse:
        data = getattr(exc, "data", None)
        return error_response(422, str(exc), data)

    return app


def error_response(
    status_code: int, message: str, data: Any = None
) -> JSONResponse:
    payload: dict[str, Any] = {
        "version": "v1",
        "ok": False,
        "error": message,
    }
    if data is not None:
        payload["data"] = data
    return JSONResponse(status_code=status_code, content=payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the independent BeeFoundrySim API backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--seed-assets", type=Path, default=None)
    parser.add_argument("--cors-origin", action="append", dest="cors_origins")
    parser.add_argument("--access-token", default=os.environ.get("BEEFOUNDRYSIM_API_TOKEN"))
    parser.add_argument("--allow-controller-execution", action="store_true")
    parser.add_argument(
        "--local-scene-root",
        type=Path,
        default=(
            Path(os.environ["BEEFOUNDRYSIM_LOCAL_SCENE_ROOT"])
            if os.environ.get("BEEFOUNDRYSIM_LOCAL_SCENE_ROOT")
            else None
        ),
        help="Root of the unpacked Architectural Brownstone asset pack",
    )
    args = parser.parse_args()
    uvicorn.run(
        create_app(
            args.data_root,
            seed_assets=args.seed_assets,
            cors_origins=args.cors_origins,
            access_token=args.access_token,
            allow_controller_execution=args.allow_controller_execution,
            local_scene_root=args.local_scene_root,
        ),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
