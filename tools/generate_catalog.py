"""Generate legacy-compatible market documents from canonical submissions, offline.

Review/governance records are maintainer inputs, never contributor assertions.
Schema code is always loaded beside this trusted script, not from --root.
"""
import argparse
import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from validate import ROOT, load_json, safe_path, validate_index, validate_manifest
from validate_presentation import validate_presentation
from validate_repository import validate_repository
from validate_python import validate_python_manifest, validate_python_catalog, validate_python_repository
from validate_governance import validate_governance, validate_reviews

MAX_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 1024


def document(path):
    path = Path(path)
    # Reject links before reading: candidate data must stay in the checkout.
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symbolic links are not catalog inputs")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Catalog input exceeds 2 MiB")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys,
                      parse_constant=lambda _: _invalid_json())


def _invalid_json():
    raise ValueError("Non-finite JSON numbers are forbidden")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property")
        result[key] = value
    return result


def submission_validator():
    schemas = [load_json(ROOT / "schemas" / name) for name in
               ("manifest.schema.json", "python-manifest.schema.json", "submission.schema.json")]
    registry = Registry()
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(schemas[-1], registry=registry)


def submissions(root):
    root = Path(root)
    paths = sorted((root / "submissions").glob("*/*.json"))
    if len(paths) > MAX_RECORDS:
        raise ValueError("More than 1024 submissions")
    records = {}
    validator = submission_validator()
    for path in paths:
        record = document(path)
        validator.validate(record)
        manifest = record["manifest"]
        if manifest["ApiVersion"] == 2:
            validate_python_manifest(manifest)
        else:
            validate_manifest(manifest)
        identity = manifest["Id"], manifest["Version"]
        for part in identity:
            safe_path(part)
        if path.relative_to(root).as_posix() != "submissions/%s/%s.json" % identity:
            raise ValueError("Submission path must match exact ID and version")
        if identity in records:
            raise ValueError("Duplicate submission identity")
        if manifest["Sha256"] != manifest["Sha256"].lower():
            raise ValueError("Canonical SHA256 must be lowercase")
        records[identity] = record
    return records


def serialize(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def generate(root):
    """Return a complete output mapping. Validate everything before any writes."""
    root = Path(root)
    records = submissions(root)
    all_manifests = [r["manifest"] for r in records.values()]
    # Both independent runtime feeds must have a closed dependency graph.
    managed = [m for m in all_manifests if m["ApiVersion"] == 1]
    python = [m for m in all_manifests if m["ApiVersion"] == 2]
    if {m["Id"] for m in managed} & {m["Id"] for m in python}:
        raise ValueError("Plugin IDs cannot change runtime across versions")
    validate_index({"SchemaVersion": 1, "Plugins": managed})
    validate_python_catalog(python)
    governance = document(root / "governance/ledger.json")
    if (root / "governance.json").exists():
        validate_governance(governance, document(root / "governance.json"))
    statuses = validate_governance(governance)
    reviews = validate_reviews(root, records)
    builtins = document(root / "catalog/builtins.json")
    validate_presentation(builtins, {"SchemaVersion": 1, "Plugins": []})
    if any(e["Metadata"]["Runtime"] != "builtin" for e in builtins["Entries"]):
        raise ValueError("Builtin source may not contain package entries")
    entries = copy.deepcopy(builtins["Entries"])
    outputs = {}
    for identity, record in records.items():
        manifest = record["manifest"]
        metadata = copy.deepcopy(record["metadata"])
        review = reviews.get(identity)
        metadata["Review"] = ({"Status": "reviewed", "Version": manifest["Version"],
                               "Sha256": manifest["Sha256"], "Reviewer": review["reviewer"],
                               "ReviewedAt": review["reviewedAt"], "Notes": review["notes"],
                               "SourceRevision": review["sourceRevision"]} if review else {
            "Status": "unreviewed", "Version": manifest["Version"], "Sha256": manifest["Sha256"],
            "Notes": "未提供独立维护者人工审核记录；校验和匹配不代表代码安全。"})
        entries.append({"Id": manifest["Id"], "Version": manifest["Version"],
                        "PackageSha256": manifest["Sha256"], "Metadata": metadata})
        # Immutable archival manifests remain even after catalog withdrawal.
        prefix = "python-plugins" if manifest["ApiVersion"] == 2 else "plugins"
        outputs[prefix + "/%s/%s/manifest.json" % identity] = manifest
    validate_presentation({"SchemaVersion": 1, "Entries": entries},
                          {"SchemaVersion": 1, "Plugins": all_manifests})
    available = {(m["Id"], m["Version"]): m for m in all_manifests
                 if statuses.get((m["Id"], m["Version"], m["Sha256"]), {}).get("status") not in ("withdrawn", "revoked")}
    # Do not advertise installable dependents of a withdrawn/revoked candidate.
    while True:
        blocked = [pin for pin, m in available.items() if any(
            (d["Id"], d["Version"]) not in available for d in m.get("Dependencies", []))]
        if not blocked:
            break
        for pin in blocked:
            del available[pin]
    manifests = [m for m in available.values() if m["ApiVersion"] == 1]
    python = [m for m in available.values() if m["ApiVersion"] == 2]
    python_repository = {"SchemaVersion": 2, "Plugins": [
        {"Id": plugin_id, "Versions": [m for m in python if m["Id"] == plugin_id]}
        for plugin_id in sorted({m["Id"] for m in python})]}
    validate_python_repository(python_repository)
    index = {"SchemaVersion": 1, "Plugins": manifests}
    validate_index(index)
    repository_plugins = {}
    for manifest in manifests:
        repository_plugins.setdefault(manifest["Id"], []).append(
            {"Version": manifest["Version"], "Manifest": manifest})
    repository = {"SchemaVersion": 1, "Plugins": [
        {"Id": plugin_id, "Versions": versions} for plugin_id, versions in repository_plugins.items()]}
    validate_repository(repository)
    python_pins = {(m["Id"], m["Version"]) for m in python}
    managed_pins = {(m["Id"], m["Version"]) for m in manifests}
    presentation = {"SchemaVersion": 1, "Entries": [e for e in entries
                    if e["PackageSha256"] is None or (e["Id"], e["Version"]) in managed_pins]}
    python_presentation = {"SchemaVersion": 1, "Entries": [e for e in entries
                           if (e["Id"], e["Version"]) in python_pins]}
    validate_presentation(presentation, index, repository)
    validate_presentation(python_presentation, {"Plugins": python})
    governance["entries"].sort(key=lambda e: (e["id"], e["version"], e["sha256"]))
    outputs.update({"index.json": index, "repository.json": repository,
                    "presentation.json": presentation, "governance.json": governance,
                    "python-repository.json": python_repository,
                    "python-presentation.json": python_presentation})
    serialized = {path: serialize(value) for path, value in outputs.items()}
    if any(len(text.encode("utf-8")) > MAX_BYTES for text in serialized.values()):
        raise ValueError("Generated document exceeds 2 MiB")
    return serialized


def synchronize(root, check=False):
    root = Path(root)
    outputs = generate(root)
    expected = set(outputs)
    existing_manifests = {p.relative_to(root).as_posix() for prefix in ("plugins", "python-plugins")
                          for p in (root / prefix).glob("*/*/manifest.json")}
    if existing_manifests - expected:
        raise ValueError("Archival manifest has no canonical submission; do not delete release history")
    stale = []
    for relative, text in outputs.items():
        path = root / relative
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Symbolic links are not generated catalog targets")
        if path.exists():
            current = document(path)
            if relative.startswith(("plugins/", "python-plugins/")) and current != json.loads(text):
                raise ValueError("Published archival manifests are immutable")
        if not path.exists() or path.read_bytes() != text.encode("utf-8"):
            stale.append(relative)
    if check and stale:
        raise ValueError("Generated catalog is stale: " + ", ".join(stale))
    if not check:
        for relative in stale:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(outputs[relative], encoding="utf-8", newline="\n")
    return len(outputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="Read-only: fail on generated drift")
    args = parser.parse_args()
    count = synchronize(args.root, args.check)
    print(f"Catalog OK: {count} generated documents; no downloads, builds or plugin execution")


if __name__ == "__main__":
    main()
