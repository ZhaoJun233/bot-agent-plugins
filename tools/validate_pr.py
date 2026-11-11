"""Trusted-base, offline candidate DATA validator. Never import candidate code."""
import argparse
import hashlib
import os
import re
from pathlib import Path

from generate_catalog import MAX_BYTES, document, generate, submissions
from validate import ROOT
from validate_governance import validate_governance

GENERATED = {"index.json", "repository.json", "presentation.json",
             "python-repository.json", "python-presentation.json"}
SUBMISSION = re.compile(r"submissions/[a-z][a-z0-9.-]{0,79}/[0-9A-Za-z.-]{1,80}\.json")
ARCHIVE = re.compile(r"(?:plugins|python-plugins)/[a-z][a-z0-9.-]{0,79}/[0-9A-Za-z.-]{1,80}/manifest\.json")
REVIEW = re.compile(r"reviews/[a-z][a-z0-9.-]{0,79}/[0-9A-Za-z.-]{1,80}\.json")
MAX_TREE_BYTES = 32 * 1024 * 1024


def tree(root):
    root = Path(root)
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("Candidate tree contains symbolic links")
    result = {}
    total = 0
    visited = 0
    # Prune checkout internals before traversal, and bound directories as well as files.
    def walk_error(error):
        raise ValueError("Cannot enumerate candidate data") from error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        parent = Path(directory)
        if parent == root:
            dirs[:] = [name for name in dirs if name != ".git"]
            files = [name for name in files if name != ".git"]
        visited += len(dirs) + len(files)
        if visited > 10000:
            raise ValueError("Candidate tree exceeds bounded data budget")
        for name in dirs + files:
            if (parent / name).is_symlink():
                raise ValueError("Candidate tree contains symbolic links")
        for name in files:
            path = parent / name
            if not path.is_file():
                raise ValueError("Candidate tree contains a non-regular file")
            size = path.stat().st_size
            total += size
            if size > MAX_BYTES or total > MAX_TREE_BYTES:
                raise ValueError("Candidate tree exceeds bounded data budget")
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def validate_candidate(base, candidate, lane="contributor"):
    if lane not in ("contributor", "maintainer"):
        raise ValueError("Unknown validation lane")
    base, candidate = Path(base), Path(candidate)
    before, after = tree(base), tree(candidate)
    changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
    for path in changed:
        allowed = path in GENERATED or SUBMISSION.fullmatch(path) or ARCHIVE.fullmatch(path)
        if lane == "maintainer":
            allowed = allowed or REVIEW.fullmatch(path) or path in {
                "governance/ledger.json", "governance.json", "catalog/builtins.json"}
        if not allowed:
            raise ValueError("Protected/non-submission path changed: " + path)
    previous = submissions(base)
    current = submissions(candidate)
    for identity, record in previous.items():
        if identity not in current or current[identity]["manifest"] != record["manifest"]:
            raise ValueError("Published id/version manifest cannot change or disappear")
    for path in before:
        if ARCHIVE.fullmatch(path) and (path not in after or document(base / path) != document(candidate / path)):
            raise ValueError("Published archival manifest cannot change or disappear")
    feed = document(candidate / "governance/ledger.json")
    for old_path in (base / "governance/ledger.json", base / "governance.json"):
        if old_path.exists():
            validate_governance(feed, document(old_path))
    outputs = generate(candidate)
    for path, expected in outputs.items():
        target = candidate / path
        if not target.exists() or target.read_bytes() != expected.encode("utf-8"):
            raise ValueError("Generated catalog drift: " + path)
    actual_archives = {p for p in after if p.startswith(("plugins/", "python-plugins/"))}
    expected_archives = {p for p in outputs if p.startswith(("plugins/", "python-plugins/"))}
    if actual_archives != expected_archives:
        raise ValueError("Unexpected archival output")
    for path in after:
        if path.startswith("submissions/") and not SUBMISSION.fullmatch(path):
            raise ValueError("Non-canonical submission path")
        if path.startswith("reviews/") and not REVIEW.fullmatch(path):
            raise ValueError("Non-canonical review path")
    return len(changed), len(outputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--lane", choices=("contributor", "maintainer"), default="contributor")
    args = parser.parse_args()
    changed, outputs = validate_candidate(args.base, args.candidate, args.lane)
    print(f"{args.lane} DATA validation OK: {changed} changed paths; {outputs} generated documents")


if __name__ == "__main__":
    main()
