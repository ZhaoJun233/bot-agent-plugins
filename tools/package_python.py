"""Deterministic stdlib-only worker packager, never executes Python sources."""
import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

from validate import MAX_ARCHIVE, safe_path
from validate_python import SDK_FILENAME, validate_python_manifest, validate_python_archive


def package_python(source, output, manifest, *, sdk):
    source, output = Path(source), Path(output)
    manifest = dict(manifest)
    validate_python_manifest(manifest)
    if sdk is None:
        raise ValueError("Python packaging requires explicit canonical host --sdk path")
    sdk = Path(sdk)
    for path in (source, sdk, output):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Package paths may not contain symbolic links")
    if not source.is_dir() or not sdk.is_file() or sdk.name != SDK_FILENAME:
        raise ValueError("Expected source directory and canonical botagent_worker.py file")
    if output.resolve().is_relative_to(source.resolve()):
        raise ValueError("Package output must be outside the source tree")
    files, total = {}, sdk.stat().st_size
    visited = 0
    for directory, dirs, names in os.walk(source, followlinks=False):
        visited += len(dirs) + len(names)
        if visited > 2048:
            raise ValueError("Too many Python package entries")
        for name in dirs + names:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("Python package links forbidden")
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(source).as_posix()
            safe_path(relative)
            if relative.casefold() == SDK_FILENAME:
                raise ValueError("Do not vendor the SDK; supply canonical host --sdk")
            if not path.is_file():
                raise ValueError("Only regular source assets allowed")
            total += path.stat().st_size
            if total > MAX_ARCHIVE:
                raise ValueError("Python source assets exceed package budget")
            files[relative] = path
    if not files or len(files) + 1 > 2048 or total > MAX_ARCHIVE:
        raise ValueError("Invalid Python source asset budget")
    files[SDK_FILENAME] = sdk
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_STORED) as bundle:
        for name, path in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
    blob = payload.getvalue()
    manifest["Sha256"] = hashlib.sha256(blob).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (manifest["Id"] + "-" + manifest["Version"] + ".zip")
    if archive.exists() and archive.read_bytes() != blob:
        raise ValueError("An existing versioned ZIP is immutable")
    # Validate before replacing any final versioned artifact.
    with tempfile.NamedTemporaryFile(dir=output, suffix=".zip", delete=False) as temp:
        temporary = Path(temp.name)
        temp.write(blob)
    try:
        validate_python_archive(temporary, manifest)
    finally:
        temporary.unlink()
    archive.write_bytes(blob)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text(manifest["Sha256"] + "  " + archive.name + "\n", encoding="utf-8")
    return archive, manifest
