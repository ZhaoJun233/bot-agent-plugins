"""Synthetic M5 producer boundaries; no worker execution/network/package install."""
import copy
import hashlib
import json
import shutil
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from jsonschema import ValidationError
from generate_catalog import ROOT, document, generate, synchronize
from package import package
from validate import validate_index, validate_manifest
from validate_python import validate_python_manifest, validate_python_repository, validate_python_archive
from validate_pr import validate_candidate
from verify_release import verify_release

FIXTURE = document(ROOT / "tests/fixtures/python-contract.json")
ID = FIXTURE["manifest"]["Id"]
SUBMISSION = "submissions/" + ID + "/1.0.0.json"
ARCHIVE = "python-plugins/" + ID + "/1.0.0/manifest.json"
ERRORS = (ValueError, ValidationError)

class PythonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = copy.deepcopy(FIXTURE["manifest"])
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "worker.py").write_text("raise AssertionError('must not execute')\n", encoding="utf-8")
        self.sdk = self.root / "botagent_worker.py"
        self.sdk.write_text("# Synthetic SDK bytes; never executed\n", encoding="utf-8")

    def catalog(self):
        root = self.root / "catalog"
        shutil.copytree(ROOT / "catalog", root / "catalog")
        (root / "governance").mkdir()
        (root / "governance/ledger.json").write_text(json.dumps({"schemaVersion": 1,
            "generatedAt": "2026-11-06T00:00:00Z", "entries": []}), encoding="utf-8")
        hello = Path("submissions/community.example.hello/1.0.0.json")
        (root / hello).parent.mkdir(parents=True)
        shutil.copy2(ROOT / hello, root / hello)
        record = document(ROOT / "submissions/community.example.hello/1.0.0.json")
        record["manifest"] = self.manifest
        record["metadata"]["Runtime"] = "python"
        record["metadata"]["Compatibility"] = "需要宿主配置 Python 3.11 或更新的 3.x；仅标准库。"
        path = root / SUBMISSION
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        synchronize(root)
        return root

    def archive(self, extras=None, omitted=()):
        path = self.root / "input.zip"
        assets = {"worker.py": b"# synthetic\n", "botagent_worker.py": b"# synthetic SDK\n"}
        assets.update(extras or {})
        with zipfile.ZipFile(path, "w") as bundle:
            for name, content in assets.items():
                if name not in omitted:
                    info = zipfile.ZipInfo(name)
                    info.filename = name  # Preserve malicious backslashes on Windows too.
                    bundle.writestr(info, content)
        manifest = copy.deepcopy(self.manifest)
        manifest["Sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path, manifest

    def test_shared_contract_boundaries(self):
        validate_python_manifest(self.manifest)
        for case in FIXTURE["runtimeCases"]:
            value = copy.deepcopy(self.manifest)
            value["Runtime"][case["field"]] = case["value"]
            with self.subTest(case=case["name"]):
                if case["accepted"]:
                    validate_python_manifest(value)
                else:
                    with self.assertRaises(ERRORS): validate_python_manifest(value)

    def test_api_discriminator_rejects_mixed_managed_fields(self):
        for field in ("EntryAssembly", "EntryType", "TargetFramework"):
            with self.subTest(field=field), self.assertRaises(ERRORS):
                validate_python_manifest(dict(self.manifest, **{field: "dummy"}))
        with self.assertRaises(ERRORS): validate_manifest(self.manifest)
        with self.assertRaises(ERRORS): validate_index({"SchemaVersion": 1, "Plugins": [self.manifest]})
        managed = document(ROOT / "submissions/community.example.hello/1.0.0.json")["manifest"]
        managed["Runtime"] = None
        with self.assertRaises(ERRORS): validate_manifest(managed)

    def test_exact_protocol_and_api_integer(self):
        for value in (True, 1.0, "1", 2):
            manifest = copy.deepcopy(self.manifest)
            manifest["Runtime"]["ProtocolVersion"] = value
            with self.subTest(value=value), self.assertRaises(ERRORS): validate_python_manifest(manifest)
        for value in (2.0, True, "2"):
            with self.assertRaises(ERRORS): validate_python_manifest(dict(self.manifest, ApiVersion=value))

    def test_runtime_missing_unknown_and_sdk_entry_rejected(self):
        for value in (None, {}, dict(self.manifest["Runtime"], Unknown=True), dict(self.manifest["Runtime"], EntryPoint="botagent_worker.py")):
            with self.assertRaises(ERRORS): validate_python_manifest(dict(self.manifest, Runtime=value))

    def test_repository_grouped_identity_and_empty(self):
        self.assertEqual([], validate_python_repository({"SchemaVersion": 2, "Plugins": []}))
        doc = {"SchemaVersion": 2, "Plugins": [{"Id": ID, "Versions": [self.manifest]}]}
        self.assertEqual([self.manifest], validate_python_repository(doc))
        for bad in ({"SchemaVersion": 2, "Plugins": [self.manifest]}, {"SchemaVersion": 2, "Releases": [self.manifest]}, dict(doc, SchemaVersion=2.0)):
            with self.assertRaises(ERRORS): validate_python_repository(bad)
        doc["Plugins"][0]["Id"] = "another.id"
        with self.assertRaises(ERRORS): validate_python_repository(doc)

    def test_repository_duplicates_and_dependency_closure(self):
        group = {"Id": ID, "Versions": [self.manifest]}
        with self.assertRaises(ERRORS): validate_python_repository({"SchemaVersion": 2, "Plugins": [group, group]})
        group["Versions"].append(self.manifest)
        with self.assertRaises(ERRORS): validate_python_repository({"SchemaVersion": 2, "Plugins": [group]})
        self.manifest["Dependencies"] = [{"Id": "missing.plugin", "Version": "1.0.0"}]
        with self.assertRaises(ERRORS): validate_python_repository({"SchemaVersion": 2, "Plugins": [{"Id": ID, "Versions": [self.manifest]}]})

    def test_separate_catalogs_and_metadata(self):
        root = self.catalog()
        outputs = generate(root)
        for name in ("index.json", "repository.json", "presentation.json"):
            self.assertNotIn(ID, outputs[name])
        self.assertIn(ID, outputs["python-repository.json"])
        self.assertIn(ID, outputs["python-presentation.json"])
        self.assertIn(ARCHIVE, outputs)
        self.assertNotIn(ARCHIVE.removeprefix("python-"), outputs)
        self.assertEqual(outputs, generate(root))
        synchronize(root, check=True)

    def test_mismatched_presentation_runtime_rejected(self):
        root = self.catalog()
        record = document(root / SUBMISSION)
        record["metadata"]["Runtime"] = "dotnet"
        (root / SUBMISSION).write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(ERRORS): generate(root)

    def test_contributor_data_path_and_immutability(self):
        base = self.catalog()
        candidate = self.root / "candidate"
        shutil.copytree(base, candidate)
        record = document(candidate / SUBMISSION)
        record["metadata"]["Summary"] = "合成 Python 摘要更新。"
        (candidate / SUBMISSION).write_text(json.dumps(record), encoding="utf-8")
        synchronize(candidate)
        self.assertGreater(validate_candidate(base, candidate)[0], 0)
        record["manifest"]["Runtime"]["Tools"] = ["other"]
        (candidate / SUBMISSION).write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(ERRORS): validate_candidate(base, candidate)

    def test_archive_path_cannot_be_silently_removed(self):
        root = self.catalog()
        other = root / "python-plugins/extra.id/1.0.0/manifest.json"
        other.parent.mkdir(parents=True)
        other.write_text("{}")
        with self.assertRaises(ERRORS): synchronize(root)

    def test_governance_delists_python_but_keeps_tombstone_descriptor(self):
        root = self.catalog()
        for status in ("deprecated", "withdrawn", "revoked"):
            ledger = {"schemaVersion": 1, "generatedAt": "2026-11-06T02:00:00Z", "entries": [{"id": ID, "version": "1.0.0", "sha256": self.manifest["Sha256"], "status": status, "reason": "Synthetic governance", "updatedAt": "2026-11-06T02:00:00Z"}]}
            (root / "governance/ledger.json").write_text(json.dumps(ledger))
            output = generate(root)
            self.assertIn(ARCHIVE, output)
            self.assertEqual(status == "deprecated", ID in output["python-repository.json"])
            self.assertEqual(status == "deprecated", ID in output["python-presentation.json"])
            self.assertIn(ID, output["governance.json"])

    def test_review_provenance_is_separate(self):
        root = self.catalog()
        record = document(root / SUBMISSION)
        record["metadata"]["Review"] = {"Status": "reviewed"}
        (root / SUBMISSION).write_text(json.dumps(record))
        with self.assertRaises(ERRORS): generate(root)

    def test_package_explicit_sdk_and_determinism(self):
        with self.assertRaisesRegex(ValueError, "canonical"): package(self.source, self.root / "out", self.manifest)
        with patch("socket.create_connection", side_effect=AssertionError("network")), patch("subprocess.run", side_effect=AssertionError("execution")):
            path, manifest = package(self.source, self.root / "out1", self.manifest, sdk=self.sdk)
            second, same = package(self.source, self.root / "out2", self.manifest, sdk=self.sdk)
            self.assertEqual(path.read_bytes(), second.read_bytes())
            self.assertEqual(manifest, same)
            with zipfile.ZipFile(path) as bundle:
                self.assertEqual(self.sdk.read_bytes(), bundle.read("botagent_worker.py"))
            validate_python_archive(path, manifest)
            verify_release(self.root / "out1/manifest.json", path, second)

    def test_package_rejects_vendored_sdk_and_output_in_source(self):
        with self.assertRaises(ValueError): package(self.source, self.source / "out", self.manifest, sdk=self.sdk)
        (self.source / "botagent_worker.py").write_text("# stale SDK")
        with self.assertRaisesRegex(ValueError, "vendor"): package(self.source, self.root / "out", self.manifest, sdk=self.sdk)

    def test_versioned_python_artifact_immutable(self):
        path, manifest = package(self.source, self.root / "out", self.manifest, sdk=self.sdk)
        before = path.read_bytes()
        (self.source / "worker.py").write_text("# different")
        with self.assertRaisesRegex(ValueError, "immutable"): package(self.source, self.root / "out", self.manifest, sdk=self.sdk)
        self.assertEqual(before, path.read_bytes())

    def test_hash_mismatch(self):
        path, manifest = self.archive()
        manifest["Sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SHA256"): validate_python_archive(path, manifest)

    def test_archive_requires_both_entry_and_sdk(self):
        for omitted in ("worker.py", "botagent_worker.py"):
            path, manifest = self.archive(omitted=(omitted,))
            with self.assertRaisesRegex(ValueError, "missing"): validate_python_archive(path, manifest)

    def test_archive_refuses_executable_dependencies_and_unsafe_paths(self):
        for name in ("dependency.dll", "extension.pyd", "wheel.whl", "setup.py", "requirements.txt", "venv/data.json", "site-packages/lib.py", "__pycache__/x.py", "../x.py", "a\\x.py", "con.py", "install.sh"):
            with self.subTest(name=name):
                path, manifest = self.archive({name: b"# synthetic"})
                with self.assertRaises(ERRORS): validate_python_archive(path, manifest)

    def test_archive_rejects_case_collision_and_symlink(self):
        path, manifest = self.archive({"Worker.py": b"# duplicate"})
        with self.assertRaisesRegex(ValueError, "Duplicate"): validate_python_archive(path, manifest)
        path, manifest = self.archive()
        with zipfile.ZipFile(path, "a") as bundle:
            info = zipfile.ZipInfo("link.py")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            bundle.writestr(info, "worker.py")
        manifest["Sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "Symlink"): validate_python_archive(path, manifest)

    def test_archive_rejects_special_mode_and_file_parent(self):
        path, manifest = self.archive({"data.json": b"{}", "data.json/child.py": b"# child"})
        with self.assertRaisesRegex(ValueError, "conflicts"): validate_python_archive(path, manifest)
        path, manifest = self.archive()
        with zipfile.ZipFile(path, "a") as bundle:
            info = zipfile.ZipInfo("fifo.py")
            info.external_attr = (stat.S_IFIFO | 0o644) << 16
            bundle.writestr(info, "# passive")
        manifest["Sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "Nonregular"): validate_python_archive(path, manifest)

    def test_repository_total_document_and_candidate_budgets(self):
        with self.assertRaisesRegex(ValueError, "2 MiB"):
            validate_python_repository({"padding": "x" * (2 * 1024 * 1024)})
        entry = {"Id": ID, "Versions": [self.manifest] * 128}
        with self.assertRaisesRegex(ValueError, "1024"):
            validate_python_repository({"SchemaVersion": 2, "Plugins": [entry] * 9})

    def test_iterative_graph_handles_maximum_chain(self):
        from validate import validate_dependency_graph
        manifests = [{"Id": "chain.%d" % i, "Version": "1.0.0", "Dependencies": ([{"Id": "chain.%d" % (i - 1), "Version": "1.0.0"}] if i else [])} for i in range(1024)]
        validate_dependency_graph(manifests)
        manifests[0]["Dependencies"] = [{"Id": "chain.1023", "Version": "1.0.0"}]
        with self.assertRaisesRegex(ValueError, "cycle"): validate_dependency_graph(manifests)

    def test_archive_requires_utf8_source_without_executing(self):
        path, manifest = self.archive({"bad.py": b"\xff"})
        with self.assertRaises(UnicodeError): validate_python_archive(path, manifest)

if __name__ == "__main__":
    unittest.main()
