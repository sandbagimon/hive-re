from __future__ import annotations

import io
import shutil
import stat
import uuid
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from beefoundrysim.services.openusd.stage_loader import SUPPORTED_USD_EXTENSIONS

MAX_UPLOAD_BYTES = 256 * 1024 * 1024
MAX_UPLOAD_FILES = 4096
STREAM_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class StagedOpenUsdUpload:
    root: Path
    entry_path: Path
    file_count: int
    byte_count: int


def safe_relative_path(raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/")
    path = Path(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or ":" in path.parts[0]
        or ".." in path.parts
        or path.is_absolute()
    ):
        raise ValueError(f"Unsafe uploaded path: {raw_path}")
    return path


def stage_openusd_streams(
    project_root: str | Path,
    files: Iterable[tuple[str, BinaryIO]],
    entry_name: str,
    *,
    package_entry: str | None = None,
) -> StagedOpenUsdUpload:
    root = Path(project_root).resolve()
    upload_root = root / "assets" / "uploads" / uuid.uuid4().hex
    upload_root.mkdir(parents=True, exist_ok=False)
    byte_count = 0
    file_count = 0
    paths: set[Path] = set()
    try:
        for raw_name, stream in files:
            relative = safe_relative_path(raw_name)
            if relative in paths:
                raise ValueError(f"Duplicate uploaded path: {relative.as_posix()}")
            paths.add(relative)
            file_count += 1
            if file_count > MAX_UPLOAD_FILES:
                raise ValueError(f"OpenUSD upload exceeds {MAX_UPLOAD_FILES} files")
            output = upload_root / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("wb") as destination:
                while True:
                    chunk = stream.read(STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    byte_count += len(chunk)
                    if byte_count > MAX_UPLOAD_BYTES:
                        raise ValueError("OpenUSD upload bundle exceeds 256 MiB")
                    destination.write(chunk)

        entry_relative = safe_relative_path(entry_name)
        entry_path = upload_root / entry_relative
        if not entry_path.is_file():
            raise ValueError(f"OpenUSD entry file is not present in upload: {entry_name}")
        if entry_path.suffix.lower() == ".zip":
            entry_path, extracted_count, extracted_bytes = _extract_zip_package(
                entry_path,
                upload_root / "package",
                package_entry=package_entry,
            )
            file_count += extracted_count
            byte_count += extracted_bytes
            if file_count > MAX_UPLOAD_FILES:
                raise ValueError(f"OpenUSD package exceeds {MAX_UPLOAD_FILES} files")
            if byte_count > MAX_UPLOAD_BYTES:
                raise ValueError("OpenUSD upload bundle exceeds 256 MiB")
        elif entry_path.suffix.lower() not in SUPPORTED_USD_EXTENSIONS:
            expected = ", ".join(sorted([*SUPPORTED_USD_EXTENSIONS, ".zip"]))
            raise ValueError(f"Unsupported OpenUSD entry extension. Expected one of: {expected}")
        return StagedOpenUsdUpload(upload_root, entry_path, file_count, byte_count)
    except Exception:
        shutil.rmtree(upload_root, ignore_errors=True)
        raise


def stage_openusd_bytes(
    project_root: str | Path,
    files: Iterable[tuple[str, bytes]],
    entry_name: str,
    *,
    package_entry: str | None = None,
) -> StagedOpenUsdUpload:
    streams = [(name, io.BytesIO(content)) for name, content in files]
    return stage_openusd_streams(
        project_root,
        streams,
        entry_name,
        package_entry=package_entry,
    )


def _extract_zip_package(
    archive_path: Path,
    destination: Path,
    *,
    package_entry: str | None,
) -> tuple[Path, int, int]:
    destination.mkdir(parents=True, exist_ok=False)
    extracted_count = 0
    extracted_bytes = 0
    extracted_paths: set[Path] = set()
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > MAX_UPLOAD_FILES:
            raise ValueError(f"OpenUSD ZIP package exceeds {MAX_UPLOAD_FILES} entries")
        for member in members:
            relative = safe_relative_path(member.filename)
            if relative in extracted_paths:
                raise ValueError(
                    f"OpenUSD ZIP package contains a duplicate path: {relative}"
                )
            extracted_paths.add(relative)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"OpenUSD ZIP package contains a symbolic link: {relative}")
            if member.is_dir():
                (destination / relative).mkdir(parents=True, exist_ok=True)
                continue
            extracted_count += 1
            extracted_bytes += member.file_size
            if extracted_bytes > MAX_UPLOAD_BYTES:
                raise ValueError("OpenUSD ZIP package expands beyond 256 MiB")
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, output.open("wb") as target:
                shutil.copyfileobj(source, target, STREAM_CHUNK_BYTES)

    if package_entry is not None:
        selected = destination / safe_relative_path(package_entry)
        if not selected.is_file():
            raise ValueError(f"OpenUSD package entry is missing: {package_entry}")
        if selected.suffix.lower() not in SUPPORTED_USD_EXTENSIONS:
            raise ValueError(f"OpenUSD package entry is not a USD file: {package_entry}")
        return selected, extracted_count, extracted_bytes

    candidates = sorted(
        (
            path
            for path in destination.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_USD_EXTENSIONS
        ),
        key=lambda path: (len(path.relative_to(destination).parts), path.as_posix()),
    )
    if not candidates:
        raise ValueError("OpenUSD ZIP package contains no USD entry file")
    shallowest_depth = len(candidates[0].relative_to(destination).parts)
    shallowest = [
        path
        for path in candidates
        if len(path.relative_to(destination).parts) == shallowest_depth
    ]
    if len(shallowest) != 1:
        names = ", ".join(path.relative_to(destination).as_posix() for path in shallowest[:8])
        raise ValueError(
            "OpenUSD ZIP package has multiple possible entry files; "
            f"set package_entry explicitly. Candidates: {names}"
        )
    return shallowest[0], extracted_count, extracted_bytes
