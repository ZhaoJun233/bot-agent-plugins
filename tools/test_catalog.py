"""Synthetic/offline M4 security, provenance and determinism regressions."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jsonschema import ValidationError

from generate_catalog import ROOT, MAX_BYTES, document, generate, synchronize
from validate_governance import validate_governance
from validate_pr import validate_candidate

IDENTITY = ("community.example.hello", "1.0.0")
SUBMISSION = "submissions/%s/%s.json" % IDENTITY


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / "base"
        self.candidate = Path(self.temp.name) / "candidate"
        shutil.copytree(ROOT / "catalog", self.base / "catalog")
        # Transition cases share a fixed synthetic clock, independent of the
        # operational ledger refresh and additional published example versions.
        self.put("governance/ledger.json", {"schemaVersion": 1,
                 "generatedAt": "2026-11-06T00:00:00Z", "entries": []}, self.base)
        (self.base / SUBMISSION).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / SUBMISSION, self.base / SUBMISSION)
        synchronize(self.base)
        shutil.copytree(self.base, self.candidate)
        self.record = document(self.base / SUBMISSION)
        self.sha = self.record["manifest"]["Sha256"]

    def put(self, path, value, root=None):
        path = (root or self.candidate) / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def feed(self, status="revoked", sha=None):
        return {"schemaVersion": 1, "generatedAt": "2026-11-06T01:00:00Z", "entries": [{
            "id": IDENTITY[0], "version": IDENTITY[1], "sha256": sha or self.sha,
            "status": status, "reason": "Synthetic maintainer decision", "updatedAt": "2026-11-06T01:00:00Z"}]}

    def review(self):
        return {"schemaVersion": 1, "id": IDENTITY[0], "version": IDENTITY[1], "sha256": self.sha,
                "sourceRevision": "a" * 40, "reviewer": "synthetic-maintainer", "reviewedAt": "2026-11-06T00:00:00Z",
                "evidence": ["https://example.com/synthetic-evidence"], "notes": "Synthetic review only"}

    def test_deterministic_generation_and_check(self):
        first = generate(self.candidate)
        self.assertEqual(first, generate(self.candidate))
        self.assertEqual(7, synchronize(self.candidate, check=True))
        self.assertEqual((0, 7), validate_candidate(self.base, self.candidate))

    def test_drift_rejected(self):
        self.put("index.json", {"SchemaVersion": 1, "Plugins": []})
        with self.assertRaisesRegex(ValueError, "stale"):
            synchronize(self.candidate, check=True)
        with self.assertRaisesRegex(ValueError, "drift"):
            validate_candidate(self.base, self.candidate)

    def test_contributor_metadata_update_allowed(self):
        self.record["metadata"]["Summary"] = "合成测试：更新后的摘要"
        self.put(SUBMISSION, self.record)
        synchronize(self.candidate)
        validate_candidate(self.base, self.candidate)

    def test_contributor_new_version_allowed(self):
        manifest = self.record["manifest"]
        manifest["Version"] = "1.1.0"
        manifest["DownloadUrl"] = manifest["DownloadUrl"].replace("1.0.0", "1.1.0")
        self.put("submissions/%s/1.1.0.json" % IDENTITY[0], self.record)
        synchronize(self.candidate)
        self.assertEqual(8, validate_candidate(self.base, self.candidate)[1])
        repository = document(self.candidate / "repository.json")
        self.assertEqual(2, len(repository["Plugins"][0]["Versions"]))

    def test_submission_review_smuggling_rejected(self):
        for field in ("Review", "review", "Verified", "Status"):
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                record["metadata"][field] = {"Status": "reviewed"}
                self.put(SUBMISSION, record)
                with self.assertRaises(Exception):
                    generate(self.candidate)

    def test_protected_paths_rejected_without_execution(self):
        paths = ["reviews/community.example.hello/1.0.0.json", "governance/ledger.json", "governance.json",
                 "tools/validate_pr.py", "tools/requirements.txt", "schemas/manifest.schema.json",
                 ".github/workflows/validate.yml", ".github/workflows/new.yml", "catalog/builtins.json",
                 ".github/CODEOWNERS", "examples/HelloPlugin/HelloPlugin.cs", "README.md"]
        for path in paths:
            with self.subTest(path=path):
                target = self.candidate / path
                original = target.read_bytes() if target.exists() else None
                self.put(path, {"malicious": "never executed"})
                with self.assertRaisesRegex(ValueError, "Protected"):
                    validate_candidate(self.base, self.candidate)
                if original is None:
                    target.unlink()
                else:
                    target.write_bytes(original)

    def test_same_version_manifest_mutation_rejected(self):
        self.record["manifest"]["Sha256"] = "b" * 64
        self.put(SUBMISSION, self.record)
        with self.assertRaisesRegex(ValueError, "immutable"):
            synchronize(self.candidate)
        with self.assertRaisesRegex(ValueError, "cannot change"):
            validate_candidate(self.base, self.candidate)

    def test_submission_deletion_rejected(self):
        (self.candidate / SUBMISSION).unlink()
        with self.assertRaisesRegex(ValueError, "release history"):
            synchronize(self.candidate)
        with self.assertRaisesRegex(ValueError, "cannot change"):
            validate_candidate(self.base, self.candidate)

    def test_canonical_path_rejected(self):
        self.put("submissions/community.example.wrong/1.0.0.json", self.record)
        with self.assertRaisesRegex(ValueError, "path"):
            generate(self.candidate)

    def test_malformed_and_duplicate_json_rejected(self):
        for payload in ('{"schemaVersion":1,"schemaVersion":1}', '{', '{"x":NaN}'):
            (self.candidate / SUBMISSION).write_text(payload)
            with self.assertRaises((ValueError, json.JSONDecodeError)):
                document(self.candidate / SUBMISSION)

    def test_oversized_input_rejected(self):
        (self.candidate / SUBMISSION).write_text(" " * (MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "2 MiB"):
            generate(self.candidate)

    def test_symlink_rejected(self):
        path = self.candidate / "submissions/link.json"
        try:
            path.symlink_to(self.base / SUBMISSION)
        except OSError as error:
            self.skipTest("Native symlink creation unavailable: " + str(error))
        with self.assertRaisesRegex(ValueError, "Symbolic|symbolic"):
            validate_candidate(self.base, self.candidate)

    def test_deprecated_warns_without_delisting(self):
        self.put("governance/ledger.json", self.feed("deprecated"))
        synchronize(self.candidate)
        self.assertEqual(1, len(document(self.candidate / "index.json")["Plugins"]))
        self.assertEqual("deprecated", document(self.candidate / "governance.json")["entries"][0]["status"])
        validate_candidate(self.base, self.candidate, "maintainer")

    def test_withdrawn_and_revoked_delist_keep_archive(self):
        for hour, status in enumerate(("withdrawn", "revoked"), start=1):
            with self.subTest(status=status):
                feed = self.feed(status)
                feed["generatedAt"] = feed["entries"][0]["updatedAt"] = f"2026-11-06T0{hour}:00:00Z"
                self.put("governance/ledger.json", feed)
                synchronize(self.candidate)
                self.assertEqual([], document(self.candidate / "index.json")["Plugins"])
                self.assertEqual([], document(self.candidate / "repository.json")["Plugins"])
                self.assertTrue((self.candidate / ("plugins/%s/%s/manifest.json" % IDENTITY)).exists())
                validate_candidate(self.base, self.candidate, "maintainer")

    def test_withdrawal_is_reversible_not_security_revocation(self):
        self.put("governance/ledger.json", self.feed("withdrawn"))
        synchronize(self.candidate)
        restored = self.feed("deprecated")
        restored["generatedAt"] = restored["entries"][0]["updatedAt"] = "2026-11-06T02:00:00Z"
        self.put("governance/ledger.json", restored)
        synchronize(self.candidate)
        self.assertEqual(1, len(document(self.candidate / "index.json")["Plugins"]))

    def test_revoked_absent_advertisement_persists(self):
        feed = self.feed(sha="c" * 64)
        feed["entries"][0]["id"] = "community.absent"
        self.put("governance/ledger.json", feed)
        synchronize(self.candidate)
        self.assertEqual(feed, document(self.candidate / "governance.json"))
        self.assertEqual(1, len(document(self.candidate / "index.json")["Plugins"]))

    def test_revocation_cannot_be_removed_or_demoted(self):
        previous = self.feed()
        for status in (None, "withdrawn", "deprecated"):
            changed = copy.deepcopy(previous)
            if status is None:
                changed["entries"] = []
            else:
                changed["entries"][0]["status"] = status
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "terminal"):
                validate_governance(changed, previous)

    def test_candidate_cannot_rewrite_both_revocation_sources(self):
        self.put("governance/ledger.json", self.feed(), self.base)
        synchronize(self.base)
        with self.assertRaisesRegex(ValueError, "timestamp rollback|terminal"):
            validate_candidate(self.base, self.candidate, "maintainer")

    def test_governance_strict_fields_bounds_and_utc(self):
        mutations = [("sha256", "A" * 64), ("sha256", "a" * 63), ("reason", " "),
                     ("reason", "x" * 501), ("status", "active"), ("updatedAt", "2026-11-06"),
                     ("updatedAt", "2026-11-06T01:00:00+00:00"), ("updatedAt", "2026-02-30T00:00:00Z"),
                     ("id", "preset.bad"), ("version", "../1"), ("extra", True)]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                feed = self.feed()
                feed["entries"][0][key] = value
                with self.assertRaises(Exception):
                    validate_governance(feed)

    def test_governance_duplicate_and_limit(self):
        feed = self.feed()
        feed["entries"] *= 2
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_governance(feed)
        feed["entries"] *= 513
        with self.assertRaises(Exception):
            validate_governance(feed)

    def test_governance_rejects_every_control_codepoint(self):
        for codepoint in [*range(0x20), *range(0x7f, 0xa0)]:
            with self.subTest(codepoint=codepoint):
                record = self.feed()["entries"][0]
                record["reason"] = "synthetic" + chr(codepoint) + "reason"
                with self.assertRaises(ValidationError):
                    validate_governance({"schemaVersion": 1, "generatedAt": record["updatedAt"], "entries": [record]})

    def test_generator_rejects_control_reason_without_rewriting_data(self):
        outputs = ("index.json", "repository.json", "presentation.json", "governance.json")
        before = {path: (self.candidate / path).read_bytes() for path in outputs}
        for codepoint in (0, 9, 10, 13, 0x7f, 0x85):
            with self.subTest(codepoint=codepoint):
                record = self.feed()["entries"][0]
                record["reason"] = "synthetic" + chr(codepoint) + "reason"
                self.put("governance/ledger.json", {"schemaVersion": 1, "generatedAt": record["updatedAt"], "entries": [record]})
                with self.assertRaises(ValidationError):
                    synchronize(self.candidate)
                self.assertEqual(record, document(self.candidate / "governance/ledger.json")["entries"][0])
                self.assertEqual(before, {path: (self.candidate / path).read_bytes() for path in outputs})

    def test_governance_reason_uses_host_utf16_budget(self):
        for reason in ("中" * 500, chr(0x1f600) * 250, "plain public-safe reason"):
            record = self.feed()["entries"][0]
            record["reason"] = reason
            feed = {"schemaVersion": 1, "generatedAt": record["updatedAt"], "entries": [record]}
            self.assertEqual(record, next(iter(validate_governance(feed).values())))
        for reason in (chr(0x1f600) * 251, "a" * 499 + chr(0x1f600)):
            with self.subTest(length=len(reason)):
                record = self.feed()["entries"][0]
                record["reason"] = reason
                with self.assertRaisesRegex(ValueError, "500 UTF-16"):
                    validate_governance({"schemaVersion": 1, "generatedAt": record["updatedAt"], "entries": [record]})

    def test_governance_reason_rejects_invalid_unicode_surrogates(self):
        for codepoint in (0xd800, 0xdbff, 0xdc00, 0xdfff):
            record = self.feed()["entries"][0]
            record["reason"] = "synthetic" + chr(codepoint)
            with self.assertRaises(ValidationError):
                validate_governance({"schemaVersion": 1, "generatedAt": record["updatedAt"], "entries": [record]})

    def test_governance_schema_version_requires_exact_integer(self):
        validate_governance(self.feed())
        for version in (1.0, True, "1"):
            with self.subTest(version=repr(version)):
                feed = self.feed()
                feed["schemaVersion"] = version
                with self.assertRaises((ValidationError, ValueError)):
                    validate_governance(feed)

    def test_changed_governance_requires_snapshot_advance(self):
        old = self.feed("deprecated")
        old["entries"][0]["updatedAt"] = "2026-11-06T00:00:00Z"
        changed = []
        for field, value in (("reason", "Changed reason"), ("status", "withdrawn"),
                             ("updatedAt", "2026-11-06T00:30:00Z")):
            new = copy.deepcopy(old)
            new["entries"][0][field] = value
            changed.append(new)
        removed = copy.deepcopy(old)
        removed["entries"] = []
        changed.append(removed)
        added = copy.deepcopy(old)
        added["entries"].append({**old["entries"][0], "sha256": "b" * 64})
        changed.append(added)
        for new in changed:
            with self.assertRaisesRegex(ValueError, "require generatedAt to advance"):
                validate_governance(new, old)
            new["generatedAt"] = "2026-11-06T02:00:00Z"
            validate_governance(new, old)

    def test_identical_governance_replay_normalizes_order_and_snapshot_time(self):
        old = self.feed("deprecated")
        old["entries"].append({**old["entries"][0], "sha256": "b" * 64})
        new = copy.deepcopy(old)
        new["entries"].reverse()
        new["generatedAt"] = "2026-11-06T01:00:00.0000000Z"
        validate_governance(new, old)

    def test_updated_at_spelling_change_requires_snapshot_advance(self):
        old = self.feed("deprecated")
        new = copy.deepcopy(old)
        new["entries"][0]["updatedAt"] = "2026-11-06T01:00:00.0000000Z"
        with self.assertRaisesRegex(ValueError, "require generatedAt to advance"):
            validate_governance(new, old)
        new["generatedAt"] = "2026-11-06T02:00:00Z"
        validate_governance(new, old)

    def test_governance_comparison_preserves_seventh_fractional_digit(self):
        old = self.feed("deprecated")
        old["generatedAt"] = old["entries"][0]["updatedAt"] = "2026-11-06T01:00:00.0000001Z"
        new = copy.deepcopy(old)
        new["generatedAt"] = new["entries"][0]["updatedAt"] = "2026-11-06T01:00:00.0000002Z"
        new["entries"][0]["reason"] = "New snapshot at next host tick"
        validate_governance(new, old)
        with self.assertRaisesRegex(ValueError, "timestamp rollback"):
            validate_governance(old, new)
        later_update = copy.deepcopy(old)
        later_update["entries"][0]["updatedAt"] = new["generatedAt"]
        with self.assertRaisesRegex(ValueError, "update exceeds generatedAt"):
            validate_governance(later_update)

    def test_generator_rejects_float_version_and_equal_time_changes(self):
        self.put("governance/ledger.json", self.feed("deprecated"))
        synchronize(self.candidate)
        previous = (self.candidate / "governance.json").read_bytes()
        for field, value in (("schemaVersion", 1.0), ("reason", "Changed without a new snapshot")):
            feed = self.feed("deprecated")
            if field == "schemaVersion":
                feed[field] = value
            else:
                feed["entries"][0][field] = value
            self.put("governance/ledger.json", feed)
            with self.assertRaises(ValueError):
                synchronize(self.candidate)
            self.assertEqual(previous, (self.candidate / "governance.json").read_bytes())

    def test_governance_timestamps_monotonic(self):
        feed = self.feed()
        feed["entries"][0]["updatedAt"] = "2026-11-06T02:00:00Z"
        with self.assertRaisesRegex(ValueError, "exceeds"):
            validate_governance(feed)
        feed = self.feed()
        feed["generatedAt"] = "2026-11-05T00:00:00Z"
        feed["entries"] = []
        with self.assertRaisesRegex(ValueError, "rollback"):
            validate_governance(feed, self.feed())

    def test_protected_review_binds_version_hash_source_and_evidence(self):
        self.put("reviews/%s/%s.json" % IDENTITY, self.review())
        synchronize(self.candidate)
        validate_candidate(self.base, self.candidate, "maintainer")
        entry = next(e for e in document(self.candidate / "presentation.json")["Entries"] if e["Id"] == IDENTITY[0])
        self.assertEqual("reviewed", entry["Metadata"]["Review"]["Status"])
        self.assertEqual("a" * 40, entry["Metadata"]["Review"]["SourceRevision"])

    def test_stale_or_unbound_review_rejected(self):
        for key, value in (("sha256", "b" * 64), ("version", "2.0.0"), ("sourceRevision", "main"),
                           ("evidence", []), ("reviewer", " "), ("evidence", ["https://user:pass@example.com/x"])):
            with self.subTest(key=key):
                review = self.review()
                review[key] = value
                self.put("reviews/%s/%s.json" % IDENTITY, review)
                with self.assertRaises(Exception):
                    generate(self.candidate)

    def test_no_network_build_or_package_execution(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
             patch("subprocess.Popen", side_effect=AssertionError("process forbidden")):
            validate_candidate(self.base, self.candidate)

    def test_workflows_use_trusted_readonly_lanes(self):
        for name in ("validate.yml", "maintainer-review.yml"):
            text = (ROOT / ".github/workflows" / name).read_text()
            self.assertIn("contents: read", text)
            self.assertIn("working-directory: trusted", text)
            self.assertIn("persist-credentials: false", text)
            self.assertNotIn("dotnet ", text)
            self.assertNotIn("secrets.", text)
            self.assertNotIn("working-directory: candidate", text)
        self.assertIn("pull_request_target:", (ROOT / ".github/workflows/validate.yml").read_text())
        self.assertIn("environment: marketplace-review", (ROOT / ".github/workflows/maintainer-review.yml").read_text())


if __name__ == "__main__":
    unittest.main()
