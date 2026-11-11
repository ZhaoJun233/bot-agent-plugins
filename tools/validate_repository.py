"""Offline multi-version repository checks; never fetch or execute plugin code."""
import argparse
import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from validate import ROOT, load_json, validate_manifest

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES = 1024


def load_repository(path):
    path = Path(path)
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError("Repository document exceeds 2 MiB")
    return load_json(path)


@lru_cache(maxsize=1)
def repository_validator():
    schemas = [load_json(ROOT / "schemas" / name) for name in
               ("manifest.schema.json", "repository.schema.json")]
    registry = Registry()
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(schemas[1], registry=registry)


def validate_repository(document):
    """Return exact candidate manifests after shape, identity and graph checks."""
    if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise ValueError("Repository document exceeds 2 MiB")
    repository_validator().validate(document)
    if sum(len(plugin["Versions"]) for plugin in document["Plugins"]) > MAX_CANDIDATES:
        raise ValueError("Repository exceeds 1024 total candidates")
    plugin_ids, candidates = set(), {}
    for plugin in document["Plugins"]:
        plugin_id = plugin["Id"]
        if plugin_id in plugin_ids:
            raise ValueError("Duplicate repository plugin ID")
        plugin_ids.add(plugin_id)
        for version in plugin["Versions"]:
            manifest = version["Manifest"]
            if plugin_id != manifest["Id"] or version["Version"] != manifest["Version"]:
                raise ValueError("Repository identity differs from manifest")
            identity = (plugin_id, version["Version"])
            if identity in candidates:
                raise ValueError("Duplicate repository plugin version")
            validate_manifest(manifest)
            canonical_values = [manifest[key] for key in ("Id", "Version", "Sha256", "DownloadUrl")]
            canonical_values.extend(manifest.get("Permissions", []))
            for dependency in manifest.get("Dependencies", []):
                canonical_values.extend((dependency["Id"], dependency["Version"]))
            if any(value != value.strip() for value in canonical_values):
                raise ValueError("Repository manifest values must not have surrounding whitespace")
            candidates[identity] = manifest
    validate_internal_dependencies(candidates)
    return list(candidates.values())


def validate_internal_dependencies(candidates):
    # External dependencies need not be advertised by the same repository.
    # Internal cycles are rejected without recursive traversal (up to 1024 nodes).
    dependents = {identity: [] for identity in candidates}
    remaining = {identity: 0 for identity in candidates}
    for identity, manifest in candidates.items():
        for dependency in manifest.get("Dependencies", []):
            target = (dependency["Id"], dependency["Version"])
            if target in candidates:
                remaining[identity] += 1
                dependents[target].append(identity)
    ready = [identity for identity, count in remaining.items() if count == 0]
    visited = 0
    while ready:
        identity = ready.pop()
        visited += 1
        for dependent in dependents[identity]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                ready.append(dependent)
    if visited != len(candidates):
        raise ValueError("Dependency cycle in repository")


def validate_catalog_consistency(manifests, index):
    """The legacy current-version catalog must retain identical manifest objects."""
    candidates = {(m["Id"], m["Version"]): m for m in manifests}
    for manifest in index["Plugins"]:
        if candidates.get((manifest["Id"], manifest["Version"])) != manifest:
            raise ValueError("Repository does not preserve the catalog manifest")


def validate_manifest_files(manifests, root):
    for manifest in manifests:
        path = Path(root) / "plugins" / manifest["Id"] / manifest["Version"] / "manifest.json"
        if load_json(path) != manifest:
            raise ValueError("Repository differs from immutable manifest file")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT / "repository.json")
    parser.add_argument("--index", type=Path, default=ROOT / "index.json")
    parser.add_argument("--manifest-root", type=Path, default=ROOT)
    args = parser.parse_args()
    manifests = validate_repository(load_repository(args.repository))
    validate_catalog_consistency(manifests, load_json(args.index))
    validate_manifest_files(manifests, args.manifest_root)
    print(f"Repository OK: {len(manifests)} immutable candidates; no plugin code executed")


if __name__ == "__main__":
    main()