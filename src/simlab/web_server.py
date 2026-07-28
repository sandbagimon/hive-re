from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from simlab.api_v1 import create_v1_router
from simlab.resources import ResourceManager

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
) -> FastAPI:
    root = (data_root or repository_root() / ".simlab-data").resolve()
    assets = (seed_assets or repository_root() / "assets").resolve()
    manager = ResourceManager(
        root,
        assets,
        allow_controller_execution=allow_controller_execution,
    )
    app = FastAPI(
        title="SimLab API",
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
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition", "X-SimLab-Artifact-Id"],
    )
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
    parser = argparse.ArgumentParser(description="Run the independent SimLab API backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--seed-assets", type=Path, default=None)
    parser.add_argument("--cors-origin", action="append", dest="cors_origins")
    parser.add_argument("--access-token", default=os.environ.get("SIMLAB_API_TOKEN"))
    parser.add_argument("--allow-controller-execution", action="store_true")
    args = parser.parse_args()
    uvicorn.run(
        create_app(
            args.data_root,
            seed_assets=args.seed_assets,
            cors_origins=args.cors_origins,
            access_token=args.access_token,
            allow_controller_execution=args.allow_controller_execution,
        ),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
