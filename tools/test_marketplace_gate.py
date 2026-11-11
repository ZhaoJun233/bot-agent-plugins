"""Gate regressions: trust routing and stale approval identity, without GitHub writes."""
import copy
import unittest
import datetime
import json
from marketplace_gate import classify_paths, verify_premerge
from marketplace_github import GitHub, verify_pull_request


class FakeGitHub:
    repository = "example/market"
    def __init__(self):
        self.pull = {"state": "open", "base": {"sha": "a" * 40, "ref": "main", "repo": {
            "full_name": self.repository, "default_branch": "main"}},
            "head": {"sha": "b" * 40, "repo": {"full_name": "author/market"}}}
        self.status = {"context": "marketplace-gate", "state": "success", "creator": {"login": "github-actions[bot]"}}
        self.status["description"] = "Approved PR 17 base " + "a" * 40
        self.changed_stamp = "2026-01-04T00:00:00Z"
    def get(self, path):
        if path.endswith("/statuses"):
            return [self.status]
        return copy.deepcopy(self.pull)
    def file(self, path, revision):
        stamp = self.changed_stamp if revision == "b" * 40 else "2026-01-01T00:00:00Z"
        return json.dumps({"schemaVersion": 1, "generatedAt": stamp, "entries": []}).encode()


class GateTests(unittest.TestCase):
    def test_contributor_and_maintainer_have_distinct_lanes(self):
        self.assertEqual("contributor", classify_paths({"submissions/example.plugin/1.0.0.json", "repository.json"}))
        self.assertEqual("maintainer", classify_paths({"reviews/example.plugin/1.0.0.json", "presentation.json"}))
        self.assertEqual("maintainer", classify_paths({"governance.json", "governance/ledger.json"}))

    def test_tooling_has_its_own_lane_but_cannot_publish_data(self):
        self.assertEqual("tooling", classify_paths({"tools/package.py", ".github/workflows/validate.yml"}))
        for path in ("submissions/example.plugin/1.0.0.json", "repository.json", "governance.json"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "separate PRs"):
                classify_paths({"tools/validate.py", path})

    def test_unknown_and_empty_changes_are_not_approved(self):
        for paths in (set(), {".env"}, {"artifacts/plugin.zip"}, {"reviews/not-canonical.json"}):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                classify_paths(paths)

    def test_correct_fork_candidate_can_be_checked(self):
        pull = verify_pull_request(FakeGitHub(), 17, "a" * 40, "b" * 40)
        self.assertEqual("author/market", pull["head"]["repo"]["full_name"])

    def test_old_approval_cannot_cover_changed_head_or_base(self):
        for field in ("head", "base"):
            api = FakeGitHub()
            api.pull[field]["sha"] = "c" * 40
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "changed"):
                verify_pull_request(api, 17, "a" * 40, "b" * 40)

    def test_closed_wrong_repository_and_non_default_base_rejected(self):
        for mutate in (lambda p: p.update(state="closed"),
                       lambda p: p["base"]["repo"].update(full_name="other/market"),
                       lambda p: p["base"].update(ref="unprotected")):
            api = FakeGitHub()
            mutate(api.pull)
            with self.assertRaises(ValueError):
                verify_pull_request(api, 17, "a" * 40, "b" * 40)

    def test_mutable_refs_and_invalid_pr_numbers_rejected(self):
        for number, base, head in ((0, "a" * 40, "b" * 40), (True, "a" * 40, "b" * 40), (17, "main", "b" * 40), (17, "a" * 40, "latest")):
            with self.subTest(number=number, base=base, head=head), self.assertRaises(ValueError):
                verify_pull_request(FakeGitHub(), number, base, head)

    def test_api_token_cannot_follow_a_foreign_path(self):
        api = GitHub("example/market", token="synthetic-only")
        for path in ("https://example.com/steal", "/repos/other/market/pulls", "/repos/example/market-evil/pulls"):
            with self.assertRaises(ValueError):
                api.request("GET", path)

    def test_merge_rechecks_age_even_after_earlier_successful_approval(self):
        api = FakeGitHub()
        verify_premerge(api, 17, "a" * 40, "b" * 40, datetime.datetime(2026, 1, 4, 12, tzinfo=datetime.timezone.utc))
        with self.assertRaisesRegex(ValueError, "24 hours"):
            verify_premerge(api, 17, "a" * 40, "b" * 40, datetime.datetime(2026, 1, 5, 1, tzinfo=datetime.timezone.utc))

    def test_merge_requires_success_from_the_gate_workflow(self):
        for mutate in (lambda s: s.update(state="pending"), lambda s: s["creator"].update(login="another-bot")):
            api = FakeGitHub()
            mutate(api.status)
            with self.assertRaisesRegex(ValueError, "owner gate"):
                verify_premerge(api, 17, "a" * 40, "b" * 40)

    def test_old_success_cannot_be_reused_on_the_same_head_with_a_new_base(self):
        api = FakeGitHub()
        api.pull["base"]["sha"] = "c" * 40
        with self.assertRaisesRegex(ValueError, "different PR or base"):
            verify_premerge(api, 17, "c" * 40, "b" * 40)


if __name__ == "__main__":
    unittest.main()
