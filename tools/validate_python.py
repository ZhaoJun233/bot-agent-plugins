"""Python API 2 data-only validation. Never imports or executes package code."""
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from validate import (ROOT, MAX_ARCHIVE, load_json, safe_path,
                      validate_common_manifest, validate_dependency_graph)

SDK_FILENAME = "botagent_worker.py"

def validate_python_manifest(manifest):
    schema = load_json(ROOT / "schemas/python-manifest.schema.json")
    Draft202012Validator(schema).validate(manifest)
    if type(manifest["ApiVersion"]) is not int or type(manifest["Runtime"]["ProtocolVersion"]) is not int:
        raise ValueError("Python API/protocol versions require exact JSON integers")
    if len(json.dumps(manifest)) > 32768:
        raise ValueError("Manifest too large")
    validate_common_manifest(manifest)
    runtime = manifest["Runtime"]
    if not re.fullmatch(r"3\.(?:1[1-9]|[2-9][0-9])", runtime["MinimumPythonVersion"]):
        raise ValueError("Python minimum version must be canonical 3.11..3.99")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) for name in runtime["Tools"]):
        raise ValueError("Python tool names must be bounded ASCII identifiers")
    safe_path(runtime["EntryPoint"])
    if manifest["Runtime"]["EntryPoint"].casefold() == SDK_FILENAME:
        raise ValueError("Entry point cannot replace the worker SDK")

def validate_python_catalog(manifests):
    for manifest in manifests:
        validate_python_manifest(manifest)
    validate_dependency_graph(manifests)

def validate_python_repository(document):
    if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("Python repository exceeds 2 MiB")
    schema = load_json(ROOT / "schemas/python-repository.schema.json")
    manifest = load_json(ROOT / "schemas/python-manifest.schema.json")
    registry = Registry().with_resource(manifest["$id"], Resource.from_contents(manifest))
    Draft202012Validator(schema, registry=registry).validate(document)
    if type(document["SchemaVersion"]) is not int:
        raise ValueError("Python repository version requires an exact JSON integer")
    if sum(len(plugin["Versions"]) for plugin in document["Plugins"]) > 1024:
        raise ValueError("Python repository exceeds 1024 candidates")
    ids, manifests = set(), []
    for plugin in document["Plugins"]:
        if plugin["Id"] in ids:
            raise ValueError("Duplicate Python plugin ID")
        ids.add(plugin["Id"])
        for version in plugin["Versions"]:
            if version["Id"] != plugin["Id"]:
                raise ValueError("Python repository ID mismatch")
            manifests.append(version)
    validate_python_catalog(manifests)
    return manifests

def validate_python_archive(path, manifest):
    validate_python_manifest(manifest)
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Unsafe or oversized Python archive")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["Sha256"].lower():
        raise ValueError("Archive SHA256 mismatch")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > 2048:
            raise ValueError("Invalid archive entry count")
        names, files, directories, total = set(), set(), set(), 0
        for entry in entries:
            # ZipInfo normalizes backslashes/truncates NUL on Windows; inspect original spelling first.
            raw_name = entry.orig_filename
            safe_path(raw_name.rstrip("/") if entry.is_dir() else raw_name)
            name = entry.filename.rstrip("/") if entry.is_dir() else entry.filename
            safe_path(name)
            normalized = name.casefold()
            if normalized in names:
                raise ValueError("Duplicate archive entry")
            names.add(normalized)
            (directories if entry.is_dir() else files).add(normalized)
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if mode not in (0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK):
                raise ValueError("Nonregular archive entry forbidden")
            if (mode == stat.S_IFDIR and not entry.is_dir()) or (mode == stat.S_IFREG and entry.is_dir()):
                raise ValueError("Archive entry mode disagrees with path")
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise ValueError("Symlink/encrypted entry forbidden")
            # stdlib-only: source and passive data only, no installed environments/native code.
            if any(part.lower() in (".venv", "venv", "site-packages", "__pycache__") for part in name.split("/")):
                raise ValueError("Bundled dependency environment forbidden")
            if not entry.is_dir() and Path(name).suffix.lower() not in (".py", ".json", ".txt", ".md"):
                raise ValueError("Unsupported Python package asset")
            if Path(name).name.lower() in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "pip.ini"):
                raise ValueError("Dependency installation metadata forbidden")
            total += entry.file_size
            if total > MAX_ARCHIVE or entry.file_size > MAX_ARCHIVE:
                raise ValueError("Expanded archive too large")
            if entry.file_size and (not entry.compress_size or entry.file_size / entry.compress_size > 200):
                raise ValueError("Suspicious compression ratio")
        for name in names:
            if any("/".join(name.split("/")[:i]) in files for i in range(1, len(name.split("/")))):
                raise ValueError("Archive file conflicts with directory path")
        for required in (manifest["Runtime"]["EntryPoint"], SDK_FILENAME):
            if required not in [entry.filename for entry in entries if not entry.is_dir()]:
                raise ValueError("Python archive missing entry point or worker SDK")
        for entry in entries:
            if not entry.is_dir():
                payload = archive.read(entry)
                if entry.filename.lower().endswith(".py"):
                    payload.decode("utf-8")
