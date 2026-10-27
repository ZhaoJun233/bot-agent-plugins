"""Offline catalog/schema/archive checks. Downloads are an explicit separate step."""
import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
MAX_ARCHIVE = 32 * 1024 * 1024


def load_json(path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON property: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def schema_validator(name):
    schemas = [load_json(ROOT / "schemas" / item) for item in
               ("manifest.schema.json", "index.schema.json")]
    registry = Registry()
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(next(s for s in schemas if s["$id"].endswith(name)), registry=registry)


def safe_path(name):
    if not isinstance(name, str) or not name or len(name) > 240 or "\\" in name:
        raise ValueError("Unsafe package path")
    for part in name.split("/"):
        if (not part or part in (".", "..") or part.endswith((".", " "))
                or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or re.fullmatch(r"CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9]", part.split(".")[0], re.I)):
            raise ValueError("Unsafe package path")


def validate_manifest(manifest):
    schema_validator("manifest.schema.json").validate(manifest)
    if len(json.dumps(manifest)) > 32768:
        raise ValueError("Manifest too large")
    safe_path(manifest["Id"])
    safe_path(manifest["EntryAssembly"])
    minimum = manifest.get("MinimumHostVersion")
    if minimum and any(int(part) > 2147483647 for part in minimum.split(".")):
        raise ValueError("Host assembly version component out of range")
    if manifest["Sha256"] == "0" * 64:
        raise ValueError("Placeholder hash forbidden")
    url = urlsplit(manifest["DownloadUrl"])
    expected = manifest["Id"] + "-" + manifest["Version"]
    if url.path.split("/")[-2:] != [expected, expected + ".zip"]:
        raise ValueError("Release URL must pin this ID and version")
    dependency_ids = set()
    for dependency in manifest.get("Dependencies", []):
        if dependency["Id"] == manifest["Id"] or dependency["Id"] in dependency_ids:
            raise ValueError("Self or duplicate dependency")
        dependency_ids.add(dependency["Id"])
    setting_keys = set()
    for setting in manifest.get("Settings", []):
        if not setting["Label"].strip() or setting["Key"] in setting_keys:
            raise ValueError("Blank label or duplicate setting key")
        setting_keys.add(setting["Key"])
        default = setting.get("DefaultValue")
        if default is not None and setting["Type"] == "boolean" and default not in ("true", "false"):
            raise ValueError("Boolean default must be true or false")
        if default is not None and setting["Type"] == "number":
            import math
            if not math.isfinite(float(default)):
                raise ValueError("Numeric default must be finite")
        if default is not None and setting["Type"] == "select" and default not in setting["Choices"]:
            raise ValueError("Select default must be a choice")


def validate_index(index):
    schema_validator("index.schema.json").validate(index)
    pins = set()
    for manifest in index["Plugins"]:
        validate_manifest(manifest)
        pin = (manifest["Id"], manifest["Version"])
        if pin in pins:
            raise ValueError("Duplicate release")
        pins.add(pin)
    graph = {}
    for manifest in index["Plugins"]:
        node = (manifest["Id"], manifest["Version"])
        graph[node] = [(d["Id"], d["Version"]) for d in manifest.get("Dependencies", [])]
        if any(d not in pins for d in graph[node]):
            raise ValueError("Dependency not pinned in catalog")
    def visit(node, pending, done):
        if node in pending:
            raise ValueError("Dependency cycle")
        if node in done:
            return
        pending.add(node)
        for dependency in graph[node]:
            visit(dependency, pending, done)
        pending.remove(node)
        done.add(node)
    done = set()
    for node in graph:
        visit(node, set(), done)


def validate_archive(path, manifest):
    validate_manifest(manifest)
    path = Path(path)
    if path.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Archive too large")
    if hashlib.sha256(path.read_bytes()).hexdigest().lower() != manifest["Sha256"].lower():
        raise ValueError("Archive SHA256 mismatch")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > 2048:
            raise ValueError("Invalid archive entry count")
        names = set()
        total = 0
        for entry in entries:
            safe_path(entry.filename)
            normalized = entry.filename.lower()
            if normalized in names:
                raise ValueError("Duplicate archive entry")
            names.add(normalized)
            mode = entry.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG) or entry.flag_bits & 1:
                raise ValueError("Links, directories, special files or encryption forbidden")
            if not normalized.endswith(".dll") or normalized.rsplit("/", 1)[-1] == "botagent.core.dll":
                raise ValueError("Only plugin assemblies allowed; host Core forbidden")
            total += entry.file_size
            if entry.file_size > MAX_ARCHIVE or total > 128 * 1024 * 1024:
                raise ValueError("Expanded archive too large")
            payload = archive.read(entry)
            if not payload.startswith(b"MZ"):
                raise ValueError("Assembly must be a PE file")
        if manifest["EntryAssembly"].lower() not in names:
            raise ValueError("Entry assembly missing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    index = load_json(ROOT / "index.json")
    validate_index(index)
    for manifest in index["Plugins"]:
        path = ROOT / "plugins" / manifest["Id"] / manifest["Version"] / "manifest.json"
        if load_json(path) != manifest:
            raise ValueError("Catalog and release manifest differ")
        if args.archive and args.archive.name == manifest["Id"] + "-" + manifest["Version"] + ".zip":
            validate_archive(args.archive, manifest)
            args.archive = None
    if args.archive:
        raise ValueError("Archive not represented in catalog")
    print("PASS: schemas, catalog, release pins, dependency graph and requested archive")


if __name__ == "__main__":
    main()
