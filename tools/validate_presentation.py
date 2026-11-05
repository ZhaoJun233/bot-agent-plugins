"""Validate optional market presentation without changing technical package pins."""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2 * 1024 * 1024
CHINESE_FIELDS = ("Name", "Summary", "Description", "Usage", "RiskNotice", "Configuration",
                  "Compatibility", "Changelog", "PermissionNotes")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property")
        result[key] = value
    return result


def load_document(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("Presentation document exceeds 2 MiB")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)


def validate_presentation(document, index):
    schema = load_document(ROOT / "schemas/presentation.schema.json")
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(document)
    pins = {(item["Id"], item["Version"]): item for item in index["Plugins"]}
    seen = set()
    for entry in document["Entries"]:
        identity = entry["Id"], entry["Version"]
        if any(value != value.strip() for value in identity):
            raise ValueError("Identity must not contain surrounding whitespace")
        if identity in seen:
            raise ValueError("Duplicate presentation identity")
        seen.add(identity)
        metadata = entry["Metadata"]
        for field in CHINESE_FIELDS:
            if not re.search(r"[\u3400-\u9fff]", metadata[field]):
                raise ValueError("Chinese-first descriptive field required: " + field)
        for key, value in metadata.items():
            if isinstance(value, str) and not value.strip():
                raise ValueError("Blank presentation field: " + key)
        if any(not tag.strip() for tag in metadata["Tags"]):
            raise ValueError("Blank presentation tag")
        builtin = metadata["Runtime"] == "builtin"
        if builtin != (metadata["SourceKind"] == "builtin"):
            raise ValueError("Builtin source and runtime must agree")
        if builtin:
            if entry["PackageSha256"] is not None or identity in pins:
                raise ValueError("Builtin must not have a package artifact")
        else:
            pin = pins.get(identity)
            if not entry["PackageSha256"] or pin is None or entry["PackageSha256"] != pin["Sha256"]:
                raise ValueError("Presentation package identity does not match technical catalog")
            if metadata["Runtime"] != "dotnet":
                raise ValueError("Current technical catalog supports dotnet packages only")
        review = metadata["Review"]
        # jsonschema date-time checking needs an optional extra; CI must not silently skip it.
        if "ReviewedAt" in review:
            timestamp = review["ReviewedAt"]
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:[.][0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})", timestamp):
                raise ValueError("Review timestamp requires a complete date, time and timezone")
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if "SourceRevision" in review and not re.fullmatch(r"(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})", review["SourceRevision"]):
            raise ValueError("Review source revision must be an immutable 40 or 64 digit hash")
        if review["Version"] != entry["Version"] or review["Sha256"] != entry["PackageSha256"]:
            raise ValueError("Review must bind the exact version and artifact hash")
        if review["Status"] == "reviewed":
            if builtin:
                raise ValueError("Bundled functionality is not a separately reviewed package")
            if not review["Reviewer"].strip():
                raise ValueError("Reviewed record requires reviewer")
    return len(seen)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--presentation", type=Path, default=ROOT / "presentation.json")
    parser.add_argument("--index", type=Path, default=ROOT / "index.json")
    args = parser.parse_args()
    count = validate_presentation(load_document(args.presentation), load_document(args.index))
    print(f"Validated presentation v1: {count} entries; technical package pins unchanged")


if __name__ == "__main__":
    main()
