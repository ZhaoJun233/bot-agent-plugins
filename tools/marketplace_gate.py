"""Route PR checks with trusted code. Candidate code is never imported here."""
import argparse
import os
from pathlib import Path

from marketplace_github import GitHub, verify_pull_request
from governance_refresh import check_approval_age, now_utc, parse
from validate_pr import ARCHIVE, GENERATED, REVIEW, SUBMISSION, tree, validate_candidate

MAINTAINER_FILES = {"governance/ledger.json", "governance.json", "catalog/builtins.json"}
TOOLING_ROOTS = ("tools/", "schemas/", "examples/", "templates/", "sdk/", "tests/", "docs/", ".github/workflows/")
TOOLING_FILES = {".gitattributes", ".gitignore", ".github/CODEOWNERS", "Directory.Build.props", "global.json",
                 "README.md", "README.en.md", "CONTRIBUTING.md", "CONTRIBUTING.en.md", "SECURITY.md",
                 "SECURITY.en.md", "LICENSE", "NOTICE"}


def classify_paths(changed):
    if not changed:
        raise ValueError("No changes to review")
    kinds = set()
    for path in changed:
        if path in GENERATED or SUBMISSION.fullmatch(path) or ARCHIVE.fullmatch(path):
            kinds.add("contributor")
        elif path in MAINTAINER_FILES or REVIEW.fullmatch(path):
            kinds.add("maintainer")
        elif path in TOOLING_FILES or path.startswith(TOOLING_ROOTS):
            kinds.add("tooling")
        else:
            raise ValueError("Unsupported marketplace path: " + path)
    if "tooling" in kinds and len(kinds) != 1:
        raise ValueError("Source/tooling and catalog data require separate PRs")
    return "tooling" if "tooling" in kinds else "maintainer" if "maintainer" in kinds else "contributor"


def validate_routed_candidate(base, candidate):
    before, after = tree(base), tree(candidate)
    changed = {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
    lane = classify_paths(changed)
    if lane != "tooling":
        validate_candidate(base, candidate, lane)
    # Tooling is structurally bounded here; its native tests run in a separate
    # credential-free job, and every lane still requires the human gate.
    return lane, len(changed)


def candidate_governance_stamp(base, candidate):
    paths = ("governance/ledger.json", "governance.json")
    if not any((Path(base) / path).read_bytes() != (Path(candidate) / path).read_bytes() for path in paths):
        return ""
    payload = (Path(candidate) / "governance.json").read_bytes()
    check_approval_age(payload, now_utc())
    return parse(payload)["generatedAt"]


def verify_premerge(api, number, base_sha, candidate_sha, now=None):
    pull = verify_pull_request(api, number, base_sha, candidate_sha)
    statuses = api.get("/commits/" + candidate_sha + "/status")["statuses"]
    gate = next((item for item in statuses if item["context"] == "marketplace-gate"), None)
    if not gate or gate["state"] != "success" or gate["creator"]["login"] != "github-actions[bot]":
        raise ValueError("Exact candidate has no successful owner gate")
    if gate.get("description") != f"Approved PR {number} base {base_sha}":
        raise ValueError("Gate approval belongs to a different PR or base")
    paths = ("governance/ledger.json", "governance.json")
    if any(api.file(path, base_sha) != api.file(path, candidate_sha) for path in paths):
        check_approval_age(api.file("governance.json", candidate_sha), now or now_utc())
    return pull


def output(values):
    for name, value in values.items():
        value = str(value)
        if "\n" in value or "\r" in value:
            raise ValueError("Invalid workflow output")
        print(name + "=" + value)
    if destination := os.environ.get("GITHUB_OUTPUT"):
        with Path(destination).open("a", encoding="utf-8") as stream:
            for name, value in values.items():
                stream.write(name + "=" + str(value) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("inspect", "premerge"):
        inspect = actions.add_parser(action)
        inspect.add_argument("--repository", required=True)
        inspect.add_argument("--pr", type=int, required=True)
        inspect.add_argument("--base-sha", required=True)
        inspect.add_argument("--candidate-sha", required=True)
    validate = actions.add_parser("validate")
    validate.add_argument("--base", type=Path, required=True)
    validate.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    if args.action in ("inspect", "premerge"):
        verify = verify_premerge if args.action == "premerge" else verify_pull_request
        pull = verify(GitHub(args.repository), args.pr, args.base_sha, args.candidate_sha)
        output({"head_repository": pull["head"]["repo"]["full_name"]})
    else:
        lane, count = validate_routed_candidate(args.base, args.candidate)
        stamp = candidate_governance_stamp(args.base, args.candidate) if lane == "maintainer" else ""
        output({"lane": lane, "changed_files": count, "governance_stamp": stamp})


if __name__ == "__main__":
    main()
