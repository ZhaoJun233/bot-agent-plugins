"""Timestamp-only governance refresh policy; no package, review or entry edits."""
import argparse
import copy
import datetime
import json
import re
from pathlib import Path

from generate_catalog import _invalid_json, _unique_keys
from validate_governance import validate_governance

REFRESH_AFTER_HOURS = 72
ALERT_AFTER_HOURS = 120
APPROVAL_MAX_AGE_HOURS = 24
FILES = ("governance/ledger.json", "governance.json")
STAMP_FIELD = re.compile(rb'("generatedAt"[ \t\r\n]*:[ \t\r\n]*)"[^"\r\n]*"')


def utc(value):
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def parse(payload):
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError("Governance document exceeds limit")
    value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_keys,
                       parse_constant=lambda _: _invalid_json())
    validate_governance(value)
    return value


def age_hours(payload, now):
    age = (now - utc(parse(payload)["generatedAt"])).total_seconds() / 3600
    if age < -5 / 60:
        raise ValueError("Governance timestamp is in the future")
    return age


def publication_state(payload, now):
    age = age_hours(payload, now)
    return "expired" if age > ALERT_AFTER_HOURS else "refresh_due" if age >= REFRESH_AFTER_HOURS else "current"


def replace_stamp(payload, stamp):
    # Preserve entries, whitespace and all other bytes, rather than reserializing
    # the ledger and silently broadening the automation's write scope.
    updated, count = STAMP_FIELD.subn(lambda match: match[1] + b'"' + stamp.encode("ascii") + b'"', payload)
    if count != 1:
        raise ValueError("Expected one plain generatedAt field")
    before, after = parse(payload), parse(updated)
    validate_governance(after, before)
    expected = copy.deepcopy(before)
    expected["generatedAt"] = stamp
    if after != expected:
        raise ValueError("Refresh changed governance entries")
    return updated


def timestamp_only(before, after):
    stamp = parse(after)["generatedAt"]
    if replace_stamp(before, stamp) != after:
        raise ValueError("Refresh may change only generatedAt bytes")


def prepare(documents, now):
    if set(documents) != set(FILES) or parse(documents[FILES[0]]) != parse(documents[FILES[1]]):
        raise ValueError("Ledger and published governance must agree")
    if publication_state(documents[FILES[1]], now) == "current":
        return None
    stamp = now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {path: replace_stamp(payload, stamp) for path, payload in documents.items()}


def check_approval_age(payload, now):
    if age_hours(payload, now) > APPROVAL_MAX_AGE_HOURS:
        raise ValueError("Governance candidate is over 24 hours old; refresh and approve the new SHA")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    documents = {path: (args.root / path).read_bytes() for path in FILES}
    updates = prepare(documents, now_utc())
    if updates:
        for path, payload in updates.items():
            (args.root / path).write_bytes(payload)
    print("Timestamp refresh prepared" if updates else "Published timestamp is current")


if __name__ == "__main__":
    main()
