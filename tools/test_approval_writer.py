"""Execute the actual no-checkout workflow writer with an offline GitHub double."""
import copy
import datetime
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/maintainer-review.yml"


def writer_source():
    body = WORKFLOW.read_text(encoding="utf-8").split("          python3 - <<'PY'\n", 1)[1].split("          PY", 1)[0]
    return "\n".join(line[10:] for line in body.splitlines())


class ApprovalWriterTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.environment = {"GITHUB_REPOSITORY": "example/market", "BASE_SHA": "a" * 40,
                            "CANDIDATE_SHA": "b" * 40, "GITHUB_SHA": "a" * 40, "PR_NUMBER": "17",
                            "GITHUB_RUN_ID": "123", "GH_TOKEN": "synthetic-only", "GOVERNANCE_STAMP": ""}
        self.pull = {"state": "open", "base": {"sha": "a" * 40, "ref": "main", "repo": {
            "full_name": "example/market", "default_branch": "main"}}, "head": {"sha": "b" * 40}}

    def execute(self):
        owner = self
        class Opener:
            def open(self, request, **kwargs):
                owner.requests.append(request)
                return io.BytesIO(json.dumps(owner.pull if request.data is None else {"state": "success"}).encode())
        with patch.dict(os.environ, self.environment, clear=True), patch("urllib.request.build_opener", return_value=Opener()):
            exec(compile(writer_source(), str(WORKFLOW), "exec"), {})

    def test_success_is_written_only_to_exact_candidate(self):
        self.execute()
        self.assertEqual(2, len(self.requests))
        request = self.requests[-1]
        self.assertEqual("https://api.github.com/repos/example/market/statuses/" + "b" * 40, request.full_url)
        status = json.loads(request.data)
        self.assertEqual("marketplace-gate", status["context"])
        self.assertEqual("success", status["state"])
        self.assertEqual("Approved PR 17 base " + "a" * 40, status["description"])

    def test_changed_base_head_closed_pr_or_wrong_repository_never_write_success(self):
        for mutate in (lambda p: p["head"].update(sha="c" * 40), lambda p: p["base"].update(sha="c" * 40),
                       lambda p: p.update(state="closed"), lambda p: p["base"]["repo"].update(full_name="other/market")):
            original = copy.deepcopy(self.pull)
            mutate(self.pull)
            self.requests.clear()
            with self.assertRaisesRegex(SystemExit, "PR changed"):
                self.execute()
            self.assertTrue(all(request.data is None for request in self.requests))
            self.pull = original

    def test_waiting_more_than_24_hours_invalidates_timestamp_approval(self):
        self.environment["GOVERNANCE_STAMP"] = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)).isoformat()
        with self.assertRaisesRegex(SystemExit, "fresh candidate"):
            self.execute()
        self.assertEqual([], self.requests)

    def test_default_branch_run_is_not_substituted_for_approved_base(self):
        self.environment["GITHUB_SHA"] = "c" * 40
        with self.assertRaisesRegex(SystemExit, "exact protected base"):
            self.execute()
        self.assertEqual([], self.requests)

    def test_shell_syntax_in_inputs_cannot_become_a_request(self):
        self.environment["PR_NUMBER"] = "17; touch forbidden"
        with self.assertRaisesRegex(SystemExit, "Invalid repository"):
            self.execute()
        self.assertEqual([], self.requests)


if __name__ == "__main__":
    unittest.main()
