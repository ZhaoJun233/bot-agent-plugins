"""Offline governance checks. Trusted source history, not JSON, authorizes humans."""
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from validate import ROOT, load_json, safe_path


def _schema(name, value):
    schema = load_json(ROOT / "schemas" / name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


def _identity(record):
    plugin_id, version = record["id"], record["version"]
    definitions = load_json(ROOT / "schemas/manifest.schema.json")["$defs"]
    Draft202012Validator(definitions["id"]).validate(plugin_id)
    Draft202012Validator(definitions["version"]).validate(version)
    safe_path(plugin_id)
    safe_path(version)
    return record["id"], record["version"], record["sha256"]


def _utc(value):
    # Python datetime truncates after microseconds; retain the host's seventh
    # fractional digit so comparisons preserve .NET 100-nanosecond precision.
    fraction = value[:-1].partition(".")[2].ljust(7, "0")
    return datetime.fromisoformat(value.replace("Z", "+00:00")), int(fraction[6])


def _canonical_entries(records):
    # Host record equality preserves updatedAt text; only snapshot ordering
    # uses parsed instants. Equivalent updatedAt spellings are still an edit.
    return {identity: (record["status"], record["reason"], record["updatedAt"])
            for identity, record in records.items()}


def validate_governance(feed, previous=None):
    _schema("governance.schema.json", feed)
    # JSON Schema accepts 1.0 as an integer; the host wire parser does not.
    if type(feed["schemaVersion"]) is not int:
        raise ValueError("Governance schemaVersion must be an exact JSON integer")
    records = {}
    for record in feed["entries"]:
        # JSON Schema counts Unicode scalars; the host bounds .NET UTF-16 length.
        # Keep the same public-safe budget without stripping or rewriting input.
        if len(record["reason"].encode("utf-16-le")) // 2 > 500:
            raise ValueError("Governance reason exceeds 500 UTF-16 code units")
        identity = _identity(record)
        if identity in records:
            raise ValueError("Duplicate governance tuple")
        if _utc(record["updatedAt"]) > _utc(feed["generatedAt"]):
            raise ValueError("Governance update exceeds generatedAt")
        records[identity] = record
    if previous is not None:
        old = validate_governance(previous)
        if _utc(feed["generatedAt"]) < _utc(previous["generatedAt"]):
            raise ValueError("Governance timestamp rollback")
        for identity, record in old.items():
            replacement = records.get(identity)
            if record["status"] == "revoked" and (not replacement or replacement["status"] != "revoked"):
                raise ValueError("Revoked tuples are terminal and must be retained")
            if replacement and _utc(replacement["updatedAt"]) < _utc(record["updatedAt"]):
                raise ValueError("Governance update timestamp rollback")
        if (_utc(feed["generatedAt"]) == _utc(previous["generatedAt"])
                and _canonical_entries(records) != _canonical_entries(old)):
            raise ValueError("Changed governance entries require generatedAt to advance")
    return records


def validate_reviews(root, submissions):
    # Import here to share bounded, duplicate-rejecting, symlink-safe data reads.
    from generate_catalog import document
    root = Path(root)
    paths = sorted((root / "reviews").glob("*/*.json"))
    if len(paths) > 1024:
        raise ValueError("Too many review records")
    records = {}
    for path in paths:
        record = document(path)
        _schema("review.schema.json", record)
        identity = _identity(record)
        key = identity[:2]
        if path.parent.name != identity[0] or path.stem != identity[1]:
            raise ValueError("Review path must bind id/version")
        if key not in submissions or submissions[key]["manifest"]["Sha256"].lower() != identity[2]:
            raise ValueError("Review must bind exact submitted version/ZIP SHA256")
        for link in record["evidence"]:
            parsed = urlsplit(link)
            if not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Review evidence must be credential-free HTTPS")
        records[key] = record
    return records
