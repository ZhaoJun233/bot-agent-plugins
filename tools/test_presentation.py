import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from validate_presentation import ROOT, load_document, validate_presentation


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.document = load_document(ROOT / "presentation.json")
        self.index = load_document(ROOT / "index.json")
        self.package = next(e for e in self.document["Entries"] if e["PackageSha256"])
        self.builtin = next(e for e in self.document["Entries"] if e["PackageSha256"] is None)

    def validate(self):
        return validate_presentation(self.document, self.index)

    def rejected(self):
        with self.assertRaises((ValueError, jsonschema.ValidationError)):
            self.validate()

    def test_first_wave_is_eight_builtin_and_one_real_package(self):
        self.assertEqual(9, self.validate())
        self.assertEqual({"preset.feature." + x for x in (
            "music", "voice", "stickers", "poke", "vibes", "profiles", "websearch", "token-quota")},
            {e["Id"] for e in self.document["Entries"] if e["PackageSha256"] is None})
        self.assertEqual("community.example.hello", self.package["Id"])
        self.assertTrue(all(e["Metadata"]["Review"]["Status"] == "unreviewed"
                            for e in self.document["Entries"]))

    def test_rejects_future_schema(self):
        self.document["SchemaVersion"] = 2
        self.rejected()

    def test_rejects_unknown_metadata_field(self):
        self.package["Metadata"]["EntryAssembly"] = "not-executable.dll"
        self.rejected()

    def test_rejects_duplicate_identity(self):
        self.document["Entries"].append(copy.deepcopy(self.package))
        self.rejected()

    def multi_version_documents(self):
        repository = load_document(ROOT / "repository.json")
        older = copy.deepcopy(repository["Plugins"][0]["Versions"][0])
        older["Version"] = older["Manifest"]["Version"] = "0.9.0"
        older["Manifest"]["Sha256"] = "b" * 64
        older["Manifest"]["DownloadUrl"] = older["Manifest"]["DownloadUrl"].replace("1.0.0", "0.9.0")
        repository["Plugins"][0]["Versions"].append(older)
        entry = copy.deepcopy(self.package)
        entry["Version"] = entry["Metadata"]["Review"]["Version"] = "0.9.0"
        entry["PackageSha256"] = entry["Metadata"]["Review"]["Sha256"] = "b" * 64
        self.document["Entries"].append(entry)
        return repository, entry

    def test_metadata_for_noncurrent_repository_version(self):
        repository, _ = self.multi_version_documents()
        self.assertEqual(10, validate_presentation(self.document, self.index, repository))

    def test_old_index_without_repository_does_not_claim_unknown_versions(self):
        self.multi_version_documents()
        self.rejected()

    def test_noncurrent_version_still_requires_exact_hash(self):
        repository, entry = self.multi_version_documents()
        entry["PackageSha256"] = entry["Metadata"]["Review"]["Sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "technical catalog"):
            validate_presentation(self.document, self.index, repository)

    def test_repository_must_preserve_current_catalog(self):
        repository, _ = self.multi_version_documents()
        repository["Plugins"][0]["Versions"].pop(0)
        with self.assertRaisesRegex(ValueError, "preserve"):
            validate_presentation(self.document, self.index, repository)

    def test_explicit_repository_keeps_current_first_wave(self):
        repository = load_document(ROOT / "repository.json")
        self.assertEqual(9, validate_presentation(self.document, self.index, repository))

    def test_rejects_hash_mismatch(self):
        self.package["PackageSha256"] = "a" * 64
        self.rejected()

    def test_rejects_review_inherited_from_another_version(self):
        self.package["Metadata"]["Review"]["Version"] = "2.0.0"
        self.rejected()

    def test_rejects_review_inherited_from_another_artifact(self):
        self.package["Metadata"]["Review"]["Sha256"] = "b" * 64
        self.rejected()

    def test_rejects_builtin_download_identity(self):
        self.builtin["PackageSha256"] = "c" * 64
        self.rejected()

    def test_rejects_builtin_package_source_mismatch(self):
        self.builtin["Metadata"]["SourceKind"] = "official"
        self.rejected()

    def test_rejects_builtin_audit_claim(self):
        self.set_reviewed(self.builtin)
        self.rejected()

    def test_rejects_unsubstantiated_review(self):
        self.package["Metadata"]["Review"]["Status"] = "reviewed"
        self.rejected()

    def set_reviewed(self, entry):
        entry["Metadata"]["Review"].update(Status="reviewed", Reviewer="reviewer-example",
            ReviewedAt="2026-01-01T00:00:00Z", SourceRevision="d" * 40)

    def test_accepts_complete_version_bound_review_shape(self):
        self.set_reviewed(self.package)
        self.assertEqual(9, self.validate())

    def test_rejects_malformed_review_date(self):
        self.set_reviewed(self.package)
        self.package["Metadata"]["Review"]["ReviewedAt"] = "yesterday"
        self.rejected()

    def test_rejects_invalid_date_without_optional_format_extra(self):
        self.set_reviewed(self.package)
        checker = jsonschema.FormatChecker(formats=[])
        with patch("validate_presentation.jsonschema.FormatChecker", return_value=checker):
            for value in ("yesterday", "2026-02-30T00:00:00Z", "2026-01-01T00:00:00", "2026-01-01T00:00:00Z\n"):
                with self.subTest(timestamp=value):
                    self.package["Metadata"]["Review"]["ReviewedAt"] = value
                    self.rejected()

    def test_accepts_leap_day_without_optional_format_extra(self):
        self.set_reviewed(self.package)
        self.package["Metadata"]["Review"]["ReviewedAt"] = "2000-02-29T12:30:00+08:00"
        checker = jsonschema.FormatChecker(formats=[])
        with patch("validate_presentation.jsonschema.FormatChecker", return_value=checker):
            self.assertEqual(9, self.validate())

    def test_rejects_mutable_review_revision(self):
        self.set_reviewed(self.package)
        self.package["Metadata"]["Review"]["SourceRevision"] = "main"
        self.rejected()

    def test_accepts_64_digit_uppercase_source_revision(self):
        self.set_reviewed(self.package)
        self.package["Metadata"]["Review"]["SourceRevision"] = "A" * 64
        self.assertEqual(9, self.validate())

    def test_rejects_41_digit_source_revision(self):
        self.set_reviewed(self.package)
        self.package["Metadata"]["Review"]["SourceRevision"] = "a" * 41
        self.rejected()

    def test_rejects_source_revision_trailing_newline(self):
        self.set_reviewed(self.package)
        self.package["Metadata"]["Review"]["SourceRevision"] = "a" * 40 + "\n"
        self.rejected()

    def test_rejects_builtin_identity_trailing_newline(self):
        self.builtin["Id"] += "\n"
        self.rejected()

    def test_rejects_blank_tag(self):
        self.builtin["Metadata"]["Tags"] = [" "]
        self.rejected()

    def test_rejects_long_reviewer(self):
        self.set_reviewed(self.package)
        self.package["Metadata"]["Review"]["Reviewer"] = "a" * 201
        self.rejected()

    def test_rejects_blank_reviewer(self):
        self.set_reviewed(self.package)
        self.package["Metadata"]["Review"]["Reviewer"] = " "
        self.rejected()

    def test_rejects_fabricated_python_support(self):
        self.package["Metadata"]["Runtime"] = "python"
        self.rejected()

    def test_rejects_non_chinese_summary(self):
        self.package["Metadata"]["Summary"] = "English only"
        self.rejected()

    def test_rejects_repository_userinfo(self):
        self.package["Metadata"]["Repository"] = "https://user@example.com/plugin"
        self.rejected()

    def test_rejects_duplicate_json_properties(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"SchemaVersion":1,"SchemaVersion":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
                load_document(path)

    def test_rejects_oversized_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, "2 MiB"):
                load_document(path)


if __name__ == "__main__":
    unittest.main()