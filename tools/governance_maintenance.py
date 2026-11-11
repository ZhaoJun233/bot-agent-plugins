"""Trusted scheduled maintenance: prepare one PR and report publication state.

No approval, merge, Release, review or governance-entry mutation is implemented.
"""
import argparse
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from jsonschema import ValidationError

from governance_refresh import APPROVAL_MAX_AGE_HOURS, FILES, GovernanceSourceError, age_hours, now_utc, parse, prepare, publication_state, timestamp_only
from marketplace_github import GitHub, GitHubError, NoRedirect

BRANCH = "automation/governance-refresh"
TITLE = "chore(market): refresh governance publication timestamp"
ALERT_TITLE = "Marketplace governance publication needs attention"
MARKER = "<!-- marketplace-governance-maintenance -->"


def published_feed(repository, default_branch):
    if default_branch != "main":
        raise ValueError("Governance publication is configured for main")
    url = "https://raw.githubusercontent.com/" + repository + "/main/governance.json"
    request = urllib.request.Request(url, headers={"User-Agent": "bot-agent-marketplace", "Cache-Control": "no-cache"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            payload = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        raise GitHubError("public_http_" + str(error.code)) from None
    except (urllib.error.URLError, TimeoutError):
        raise GitHubError("public_unavailable") from None
    parse(payload)
    return payload


def report_state(api, state):
    issues = api.get("/issues?state=open&creator=github-actions%5Bbot%5D&per_page=100")
    matches = [issue for issue in issues if issue.get("title") == ALERT_TITLE and MARKER in (issue.get("body") or "")]
    if len(matches) > 1:
        raise ValueError("Multiple maintenance alerts require maintainer reconciliation")
    existing = matches[0] if matches else None
    healthy = state in ("current", "refresh_due")
    if healthy:
        if existing:
            api.write("POST", "/issues/" + str(existing["number"]) + "/comments", {"body": "The published governance feed is available and within the notification age limit again."})
            api.write("PATCH", "/issues/" + str(existing["number"]), {"state": "closed", "state_reason": "completed"})
        return
    body = MARKER + "\n\nPublication state: \u0060" + state + "\u0060.\nCheck the published governance feed and the pending timestamp PR. No package or approval was changed."
    if existing:
        if existing["body"] != body:
            api.write("PATCH", "/issues/" + str(existing["number"]), {"body": body})
            api.write("POST", "/issues/" + str(existing["number"]) + "/comments", {"body": "Publication state changed to \u0060" + state + "\u0060."})
    else:
        api.write("POST", "/issues", {"title": ALERT_TITLE, "body": body})


def prior_refresh(api, default_branch, base_sha):
    owner = api.repository.split("/")[0]
    pulls = api.get("/pulls?state=open&base=" + default_branch + "&head=" + owner + ":" + BRANCH + "&per_page=10")
    if len(pulls) > 1:
        raise ValueError("Multiple refresh PRs require reconciliation")
    reference = api.get("/git/ref/heads/" + BRANCH, missing_ok=True)
    if not pulls:
        if reference:
            closed = api.get("/pulls?state=closed&base=" + default_branch + "&head=" + owner + ":" + BRANCH + "&per_page=100")
            merged = [item for item in closed if item.get("merged_at") and item["head"]["sha"] == reference["object"]["sha"]
                      and item["title"] == TITLE and MARKER in (item.get("body") or "")]
            if len(merged) != 1:
                raise ValueError("Unknown or unmerged refresh branch; preserve it for maintainer review")
            verify_owned_diff(api, merged[0], base_sha)
        return None, reference
    pull = pulls[0]
    if (pull["title"] != TITLE or MARKER not in (pull.get("body") or "")
            or pull["head"]["repo"]["full_name"] != api.repository
            or not reference or reference["object"]["sha"] != pull["head"]["sha"]):
        raise ValueError("Refresh branch identity changed")
    verify_owned_diff(api, pull, base_sha)
    return pull, reference


def verify_owned_diff(api, pull, base_sha):
    changed = api.get("/pulls/" + str(pull["number"]) + "/files?per_page=100")
    if len(changed) != 2 or {item["filename"] for item in changed} != set(FILES) or any(item["status"] != "modified" for item in changed):
        raise ValueError("Existing PR contains changes beyond governance timestamps")
    head = pull["head"]["sha"]
    ancestor = api.get("/compare/" + base_sha + "..." + head)["merge_base_commit"]["sha"]
    for path in FILES:
        timestamp_only(api.file(path, ancestor), api.file(path, head))


def create_refresh(api, base_sha, default_branch, documents, updates, now):
    pull, reference = prior_refresh(api, default_branch, base_sha)
    if pull:
        head = pull["head"]["sha"]
        ancestor = api.get("/compare/" + base_sha + "..." + head)["merge_base_commit"]["sha"]
        if ancestor != base_sha:
            raise ValueError("Pending refresh base changed; preserve the candidate for maintainer reconciliation")
        if age_hours(api.file("governance.json", head), now) <= APPROVAL_MAX_AGE_HOURS:
            return {"pr_number": pull["number"], "candidate_sha": head, "base_sha": base_sha, "pending_current": True}
    base = api.get("/git/commits/" + base_sha)
    entries = []
    for path in FILES:
        timestamp_only(documents[path], updates[path])
        blob = api.write("POST", "/git/blobs", {"content": base64.b64encode(updates[path]).decode("ascii"), "encoding": "base64"})
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    tree = api.write("POST", "/git/trees", {"base_tree": base["tree"]["sha"], "tree": entries})
    parents = [base_sha]
    if reference and reference["object"]["sha"] != base_sha:
        parents.append(reference["object"]["sha"])
    commit = api.write("POST", "/git/commits", {"message": TITLE, "tree": tree["sha"], "parents": parents})
    # Recheck main before updating an owned branch. A concurrent branch change
    # also makes the non-force ref update fail instead of losing its commits.
    if api.get("/git/ref/heads/" + default_branch)["object"]["sha"] != base_sha:
        raise ValueError("Main changed during preparation; retry on its new snapshot")
    if reference:
        api.write("PATCH", "/git/refs/heads/" + BRANCH, {"sha": commit["sha"], "force": False})
    else:
        api.write("POST", "/git/refs", {"ref": "refs/heads/" + BRANCH, "sha": commit["sha"]})
    if pull is None:
        pull = api.write("POST", "/pulls", {"title": TITLE, "head": BRANCH, "base": default_branch,
            "body": MARKER + "\n\nOnly generatedAt in governance/ledger.json and governance.json changes. Maintainer approval and merge are required; this automation never approves or merges."})
    # Token-created PRs must not rely on an implicit PR event running validation.
    api.write("POST", "/actions/workflows/maintainer-review.yml/dispatches", {"ref": default_branch,
        "inputs": {"pr_number": str(pull["number"]), "base_sha": base_sha, "candidate_sha": commit["sha"]}})
    return {"pr_number": pull["number"], "candidate_sha": commit["sha"], "base_sha": base_sha}


def maintain(api, read_public=published_feed, now=None):
    now = now or now_utc()
    default_branch = "main"
    base_sha = api.get("/git/ref/heads/main")["object"]["sha"]
    try:
        published = read_public(api.repository, default_branch)
        state = publication_state(published, now)
        documents = {path: api.file(path, base_sha) for path in FILES}
        if hashlib.sha256(published).digest() != hashlib.sha256(documents["governance.json"]).digest():
            state = "public_source_mismatch"
            report_state(api, state)
            return {"state": state}
        updates = prepare(documents, now)
    except GitHubError as error:
        state = str(error) if str(error).startswith("public_") else "github_api_unavailable"
        report_state(api, state)
        return {"state": state}
    except GovernanceSourceError:
        report_state(api, "source_invalid")
        return {"state": "source_invalid"}
    except (ValueError, KeyError, UnicodeError, ValidationError):
        report_state(api, "public_invalid")
        return {"state": "public_invalid"}
    prepared = {}
    if updates is not None:
        try:
            prepared = create_refresh(api, base_sha, default_branch, documents, updates, now)
        except (ValueError, GitHubError):
            report_state(api, "refresh_blocked")
            raise
    report_state(api, state)
    return {"state": state, **prepared}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_EVENT_NAME") not in ("schedule", "workflow_dispatch")):
        raise SystemExit("Run maintenance only from the trusted main-branch workflow")
    print(json.dumps(maintain(GitHub(args.repository))))


if __name__ == "__main__":
    main()
