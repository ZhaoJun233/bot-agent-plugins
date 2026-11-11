import copy
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from validate import ROOT, load_json
from validate_repository import (load_repository, validate_repository,
                                 validate_catalog_consistency, validate_manifest_files)


def candidate(plugin_id="community.example.alpha", version="1.0.0"):
    manifest = copy.deepcopy(load_json(ROOT / "index.json")["Plugins"][0])
    manifest.update(Id=plugin_id, Version=version)
    manifest["DownloadUrl"] = ("https://github.com/example-org/example-plugins/releases/download/"
                               + plugin_id + "-" + version + "/" + plugin_id + "-" + version + ".zip")
    return {"Version": version, "Manifest": manifest}


def repository():
    return {"SchemaVersion": 1, "Plugins": [
        {"Id": "community.example.alpha", "Versions": [candidate(), candidate(version="2.0.0")]},
        {"Id": "community.example.beta", "Versions": [candidate("community.example.beta")]},
    ]}


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.document = repository()
        self.version = self.document["Plugins"][0]["Versions"][0]
        self.manifest = self.version["Manifest"]

    def rejected(self):
        with self.assertRaises((ValueError, jsonschema.ValidationError)):
            validate_repository(self.document)

    def test_multiple_plugins_and_versions(self):
        manifests = validate_repository(self.document)
        self.assertEqual(3, len(manifests))
        self.assertEqual({("community.example.alpha", "1.0.0"),
                          ("community.example.alpha", "2.0.0"),
                          ("community.example.beta", "1.0.0")},
                         {(m["Id"], m["Version"]) for m in manifests})

    def test_real_repository_preserves_existing_catalog_and_files(self):
        manifests = validate_repository(load_repository(ROOT / "repository.json"))
        self.assertEqual(1, len(manifests))
        validate_catalog_consistency(manifests, load_json(ROOT / "index.json"))
        validate_manifest_files(manifests, ROOT)

    def test_legacy_optional_fields_remain_optional(self):
        for key in ("Permissions", "Dependencies", "Settings", "TargetFramework", "MinimumHostVersion"):
            self.manifest.pop(key)
        self.assertEqual(3, len(validate_repository(self.document)))

    def test_empty_plugins_allowed_after_complete_delisting(self):
        self.document["Plugins"] = []
        self.assertEqual([], validate_repository(self.document))

    def test_empty_versions_rejected(self):
        self.document["Plugins"][0]["Versions"] = []
        self.rejected()

    def test_duplicate_plugin_rejected(self):
        self.document["Plugins"].append(copy.deepcopy(self.document["Plugins"][0]))
        self.rejected()

    def test_duplicate_version_rejected(self):
        self.document["Plugins"][0]["Versions"].append(copy.deepcopy(self.version))
        self.rejected()

    def test_id_mismatch_rejected(self):
        self.document["Plugins"][0]["Id"] = "community.example.other"
        self.rejected()

    def test_version_mismatch_rejected(self):
        self.version["Version"] = "3.0.0"
        self.rejected()

    def test_unknown_fields_rejected_at_every_layer(self):
        for position in ((), ("Plugins", 0), ("Plugins", 0, "Versions", 0),
                         ("Plugins", 0, "Versions", 0, "Manifest")):
            document = repository()
            node = document
            for key in position:
                node = node[key]
            node["Unexpected"] = True
            with self.subTest(position=position), self.assertRaises(jsonschema.ValidationError):
                validate_repository(document)

    def test_unsupported_schema_rejected(self):
        self.document["SchemaVersion"] = 2
        self.rejected()

    def test_no_new_runtime_fields_in_old_manifest(self):
        self.manifest["Runtime"] = "python"
        self.rejected()

    def test_manifest_cannot_inject_review(self):
        self.manifest["Review"] = {"Status": "reviewed"}
        self.rejected()

    def test_descriptor_cannot_override_artifact(self):
        self.version["PackageSha256"] = "b" * 64
        self.rejected()

    def test_placeholder_hash_rejected(self):
        self.manifest["Sha256"] = "0" * 64
        self.rejected()

    def test_credentialed_download_rejected(self):
        self.manifest["DownloadUrl"] = "https://user@example.com/package.zip"
        self.rejected()

    def test_query_download_rejected(self):
        self.manifest["DownloadUrl"] += "?variant=synthetic"
        self.rejected()

    def test_release_url_must_match_version(self):
        self.manifest["DownloadUrl"] = candidate(version="2.0.0")["Manifest"]["DownloadUrl"]
        self.rejected()

    def test_checksum_and_permission_newlines_rejected(self):
        for key, value in (("Sha256", self.manifest["Sha256"] + "\n"),
                           ("Permissions", ["network\n"])):
            document = repository()
            document["Plugins"][0]["Versions"][0]["Manifest"][key] = value
            with self.subTest(key=key), self.assertRaises((ValueError, jsonschema.ValidationError)):
                validate_repository(document)

    def test_total_candidate_limit_is_not_per_plugin(self):
        self.document["Plugins"][0]["Versions"] = [candidate(version=f"1.0.{n}") for n in range(600)]
        self.document["Plugins"][1]["Versions"] = [candidate("community.example.beta", f"1.0.{n}")
                                                   for n in range(425)]
        with self.assertRaisesRegex(ValueError, "1024 total"):
            validate_repository(self.document)

    def test_document_byte_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repository.json"
            path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, "2 MiB"):
                load_repository(path)
        self.document["Padding"] = "x" * (2 * 1024 * 1024)
        with self.assertRaisesRegex(ValueError, "2 MiB"):
            validate_repository(self.document)

    def test_duplicate_json_property_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repository.json"
            path.write_text('{"SchemaVersion":1,"SchemaVersion":1,"Plugins":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate JSON property"):
                load_repository(path)

    def test_external_dependency_is_allowed_but_not_assumed_installed(self):
        self.manifest["Dependencies"] = [{"Id": "community.example.external", "Version": "1.0.0"}]
        self.assertEqual(3, len(validate_repository(self.document)))

    def test_internal_dependency_cycle_rejected(self):
        self.manifest["Dependencies"] = [{"Id": "community.example.beta", "Version": "1.0.0"}]
        self.document["Plugins"][1]["Versions"][0]["Manifest"]["Dependencies"] = [
            {"Id": "community.example.alpha", "Version": "1.0.0"}]
        with self.assertRaisesRegex(ValueError, "Dependency cycle"):
            validate_repository(self.document)

    def test_internal_acyclic_dependency_allowed(self):
        self.manifest["Dependencies"] = [{"Id": "community.example.beta", "Version": "1.0.0"}]
        self.assertEqual(3, len(validate_repository(self.document)))

    def test_catalog_cannot_be_omitted_or_rewritten(self):
        index = {"Plugins": [copy.deepcopy(self.manifest)]}
        manifests = validate_repository(self.document)
        validate_catalog_consistency(manifests, index)
        index["Plugins"][0]["Sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "preserve"):
            validate_catalog_consistency(manifests, index)
        with self.assertRaisesRegex(ValueError, "preserve"):
            validate_catalog_consistency([], index)

    def test_release_manifest_file_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plugins" / self.manifest["Id"] / self.manifest["Version"] / "manifest.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self.manifest), encoding="utf-8")
            validate_manifest_files([self.manifest], directory)
            changed = copy.deepcopy(self.manifest)
            changed["Sha256"] = "b" * 64
            with self.assertRaisesRegex(ValueError, "immutable"):
                validate_manifest_files([changed], directory)


if __name__ == "__main__":
    unittest.main()