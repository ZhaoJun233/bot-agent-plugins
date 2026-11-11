"""Publication age, exact write ownership and GitHub orchestration regressions."""
import copy
import datetime
import json
import unittest
from unittest.mock import patch
from jsonschema import ValidationError

from governance_refresh import FILES, check_approval_age, parse, prepare, publication_state, timestamp_only
from governance_maintenance import BRANCH, MARKER, TITLE, maintain, prior_refresh, report_state
from marketplace_github import GitHubError

START = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


def feed(stamp="2026-01-01T00:00:00Z", entries=None):
    return (json.dumps({"schemaVersion": 1, "generatedAt": stamp, "entries": entries or []}, indent=2) + "\n").encode()


class RefreshTests(unittest.TestCase):
    def test_age_boundaries_distinguish_preparation_and_notification(self):
        for hours, state in ((71.99, "current"), (72, "refresh_due"), (120, "refresh_due"), (120.01, "expired")):
            self.assertEqual(state, publication_state(feed(), START + datetime.timedelta(hours=hours)))

    def test_future_publication_rejected(self):
        with self.assertRaisesRegex(ValueError, "future"):
            publication_state(feed(), START - datetime.timedelta(minutes=6))

    def test_refresh_preserves_revocation_bytes_and_every_other_field(self):
        entry = {"id": "example.plugin", "version": "1.0.0", "sha256": "a" * 64,
                 "status": "revoked", "reason": "Synthetic denial", "updatedAt": "2026-01-01T00:00:00Z"}
        original = feed(entries=[entry])
        updates = prepare(dict.fromkeys(FILES, original), START + datetime.timedelta(hours=72))
        for path in FILES:
            timestamp_only(original, updates[path])
            self.assertEqual([entry], parse(updates[path])["entries"])
            self.assertEqual(original.replace(b"2026-01-01T00:00:00Z", b"2026-01-04T00:00:00Z", 1), updates[path])

    def test_current_publication_does_not_create_new_candidate(self):
        self.assertIsNone(prepare(dict.fromkeys(FILES, feed()), START + datetime.timedelta(hours=71)))

    def test_ledger_feed_disagreement_and_extra_files_rejected(self):
        for documents in ({FILES[0]: feed(), FILES[1]: feed("2026-01-02T00:00:00Z")},
                          {**dict.fromkeys(FILES, feed()), "index.json": b"{}"}):
            with self.assertRaises(ValueError):
                prepare(documents, START + datetime.timedelta(hours=72))

    def test_non_timestamp_edit_and_rollback_rejected(self):
        with self.assertRaises(ValueError):
            timestamp_only(feed(), feed().replace(b'"entries": []', b'"entries": [ ]'))
        with self.assertRaisesRegex(ValueError, "rollback"):
            timestamp_only(feed("2026-01-02T00:00:00Z"), feed())

    def test_approval_age_is_rechecked_after_human_wait(self):
        check_approval_age(feed(), START + datetime.timedelta(hours=24))
        with self.assertRaisesRegex(ValueError, "24 hours"):
            check_approval_age(feed(), START + datetime.timedelta(hours=24, seconds=1))

    def test_duplicate_timestamp_and_non_json_are_invalid(self):
        for payload in (b'{}', b'not-json', b'{"schemaVersion":1,"generatedAt":"2026-01-01T00:00:00Z","generatedAt":"2026-01-02T00:00:00Z","entries":[]}'):
            with self.subTest(payload=payload), self.assertRaises((ValueError, ValidationError)):
                parse(payload)


class FakeApi:
    repository = "example/market"
    def __init__(self):
        self.calls = []
        self.issues = []
        self.reference = None
        self.pulls = []
        self.closed = []
        self.documents = dict.fromkeys(FILES, feed())
        self.candidate_documents = None
        self.base = "a" * 40
        self.head = "b" * 40
        self.new_sha = self.head
        self.changed = [{"filename": path, "status": "modified"} for path in FILES]
        self.compare = {"status": "ahead", "merge_base_commit": {"sha": self.base}}
    def file(self, path, revision):
        if revision == self.head and self.candidate_documents is not None:
            return self.candidate_documents[path]
        return self.documents[path]
    def get(self, path, **kwargs):
        if path == "/git/ref/heads/main": return {"object": {"sha": self.base}}
        if path.startswith("/issues?"): return copy.deepcopy([i for i in self.issues if i["state"] == "open"])
        if path.startswith("/pulls?state=open"): return copy.deepcopy(self.pulls)
        if path.startswith("/pulls?state=closed"): return copy.deepcopy(self.closed)
        if path == "/git/ref/heads/" + BRANCH: return self.reference
        if path.startswith("/git/commits/"): return {"tree": {"sha": "c" * 40}}
        if path.startswith("/compare/"): return self.compare
        if path.endswith("/files?per_page=100"): return self.changed
        raise AssertionError("Unexpected GET " + path)
    def write(self, method, path, data):
        self.calls.append((method, path, copy.deepcopy(data)))
        if path == "/issues":
            self.issues.append({"number": 1, "state": "open", **data})
            return self.issues[-1]
        if path == "/issues/1" and method == "PATCH": self.issues[0].update(data)
        if path == "/pulls": return {"number": 17}
        if path in ("/git/blobs", "/git/trees", "/git/commits"): return {"sha": self.new_sha}
        return None


class MaintenanceTests(unittest.TestCase):
    def pending(self, api, stamp):
        api.reference = {"object": {"sha": api.head}}
        api.pulls = [{"number": 17, "title": TITLE, "body": MARKER,
                      "head": {"sha": api.head, "repo": {"full_name": api.repository}}}]
        api.candidate_documents = dict.fromkeys(FILES, feed(stamp))

    def test_real_write_contract_creates_one_pr_and_dispatches_no_approval(self):
        api = FakeApi()
        result = maintain(api, lambda *_: feed(), START + datetime.timedelta(hours=73))
        self.assertEqual(17, result["pr_number"])
        self.assertEqual(1, sum(path == "/pulls" for _, path, _ in api.calls))
        self.assertEqual(2, sum(path == "/git/blobs" for _, path, _ in api.calls))
        dispatch = [data for _, path, data in api.calls if path.endswith("/dispatches")][0]
        self.assertEqual({"pr_number": "17", "base_sha": api.base, "candidate_sha": api.head}, dispatch["inputs"])
        self.assertFalse(any("merge" in path or "reviews" in path or "releases" in path for _, path, _ in api.calls))

    def test_current_publication_has_no_git_or_pr_writes(self):
        api = FakeApi()
        self.assertEqual({"state": "current"}, maintain(api, lambda *_: feed(), START))
        self.assertEqual([], api.calls)

    def test_fresh_pending_candidate_is_not_rewritten_or_redispatched(self):
        for hours in (73, 96):
            api = FakeApi()
            self.pending(api, "2026-01-04T00:00:00Z")
            result = maintain(api, lambda *_: feed(), START + datetime.timedelta(hours=hours))
            self.assertTrue(result["pending_current"])
            self.assertEqual(api.head, result["candidate_sha"])
            self.assertEqual([], api.calls)

    def test_unowned_branch_at_main_is_preserved(self):
        api = FakeApi()
        api.reference = {"object": {"sha": api.base}}
        with self.assertRaisesRegex(ValueError, "preserve"):
            prior_refresh(api, "main", api.base)
        self.assertEqual([], api.calls)

    def test_aged_pending_candidate_gets_new_sha_without_force_or_new_pr(self):
        api = FakeApi()
        self.pending(api, "2026-01-04T00:00:00Z")
        api.new_sha = "d" * 40
        result = maintain(api, lambda *_: feed(), START + datetime.timedelta(hours=100))
        self.assertEqual(api.new_sha, result["candidate_sha"])
        self.assertFalse(any(path == "/pulls" for _, path, _ in api.calls))
        commit = [data for _, path, data in api.calls if path == "/git/commits"][0]
        self.assertEqual([api.base, api.head], commit["parents"])
        update = [data for _, path, data in api.calls if path == "/git/refs/heads/" + BRANCH][0]
        self.assertFalse(update["force"])

    def test_squash_merged_owned_branch_can_be_reused_but_unmerged_branch_is_preserved(self):
        api = FakeApi()
        self.pending(api, "2026-01-04T00:00:00Z")
        api.closed = [{**api.pulls[0], "merged_at": "2026-01-04T01:00:00Z"}]
        api.pulls = []
        api.compare["status"] = "diverged"
        self.assertEqual((None, api.reference), prior_refresh(api, "main", api.base))
        api.closed[0]["merged_at"] = None
        with self.assertRaisesRegex(ValueError, "preserve"):
            prior_refresh(api, "main", api.base)
        self.assertEqual([], api.calls)

    def test_alert_unchanged_is_quiet_and_recovery_closes_once(self):
        api = FakeApi()
        report_state(api, "expired")
        first_count = len(api.calls)
        report_state(api, "expired")
        self.assertEqual(first_count, len(api.calls))
        report_state(api, "current")
        self.assertEqual("closed", api.issues[0]["state"])
        recovered_count = len(api.calls)
        report_state(api, "current")
        self.assertEqual(recovered_count, len(api.calls))

    def test_http_invalid_and_mismatched_publications_do_not_prepare_pr(self):
        for reader, expected in ((lambda *_: (_ for _ in ()).throw(GitHubError("public_http_404")), "public_http_404"),
                                 (lambda *_: b"{}", "public_invalid"),
                                 (lambda *_: feed("2026-01-02T00:00:00Z"), "public_source_mismatch")):
            api = FakeApi()
            self.assertEqual(expected, maintain(api, reader, START + datetime.timedelta(hours=73))["state"])
            self.assertFalse(any(path.startswith("/git/") or path == "/pulls" for _, path, _ in api.calls))

    def test_external_edits_in_owned_pr_are_preserved_and_rejected(self):
        api = FakeApi()
        api.reference = {"object": {"sha": api.head}}
        api.pulls = [{"number": 17, "title": TITLE, "body": MARKER,
                      "head": {"sha": api.head, "repo": {"full_name": api.repository}}}]
        api.changed.append({"filename": "index.json", "status": "modified"})
        with self.assertRaisesRegex(ValueError, "beyond governance"):
            prior_refresh(api, "main", api.base)
        self.assertEqual([], api.calls)

    def test_main_race_never_updates_branch(self):
        api = FakeApi()
        original_get = api.get
        reads = []
        def raced_get(path, **kwargs):
            if path == "/git/ref/heads/main":
                reads.append(path)
                if len(reads) > 1: return {"object": {"sha": "d" * 40}}
            return original_get(path, **kwargs)
        api.get = raced_get
        with self.assertRaisesRegex(ValueError, "Main changed"):
            maintain(api, lambda *_: feed(), START + datetime.timedelta(hours=73))
        self.assertFalse(any(path.startswith("/git/refs") for _, path, _ in api.calls))


if __name__ == "__main__":
    unittest.main()
