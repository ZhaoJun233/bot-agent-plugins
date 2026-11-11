"""Synthetic bytes only: these tests do not claim actual assembly compatibility."""
import json
import tempfile
import unittest
from pathlib import Path
from package import package
from validate import ROOT
from verify_release import verify_release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "assemblies"
        self.source.mkdir()
        (self.source / "Synthetic.dll").write_bytes(b"MZ synthetic DLL bytes - not executable")
        self.manifest = json.loads((ROOT / "plugins/community.example.hello/1.0.0/manifest.json").read_text())
        self.manifest.update(Id="community.synthetic", EntryAssembly="Synthetic.dll", EntryType="Synthetic.Plugin",
                             DownloadUrl="https://github.com/example/plugins/releases/download/community.synthetic-1.0.0/community.synthetic-1.0.0.zip")

    def test_generic_deterministic_package_and_pre_post(self):
        archive, manifest = package(self.source, self.root / "first", self.manifest)
        second, other = package(self.source, self.root / "second", self.manifest)
        self.assertEqual(archive.read_bytes(), second.read_bytes())
        self.assertEqual(manifest, other)
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest))
        self.assertEqual((manifest["Id"], manifest["Version"], manifest["Sha256"]), verify_release(path, archive, second))

    def test_post_copy_hash_mismatch_rejected(self):
        archive, manifest = package(self.source, self.root / "first", self.manifest)
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest))
        second = self.root / "changed.zip"
        second.write_bytes(archive.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            verify_release(path, archive, second)

    def test_host_core_excluded(self):
        (self.source / "BotAgent.Core.dll").write_bytes(b"synthetic")
        with self.assertRaisesRegex(ValueError, "redistribute"):
            package(self.source, self.root / "out", self.manifest)

    def test_existing_versioned_zip_cannot_be_overwritten(self):
        archive, _ = package(self.source, self.root / "fixed", self.manifest)
        original = archive.read_bytes()
        (self.source / "Synthetic.dll").write_bytes(b"MZ changed synthetic bytes")
        with self.assertRaisesRegex(ValueError, "immutable"):
            package(self.source, self.root / "fixed", self.manifest)
        self.assertEqual(original, archive.read_bytes())

    def test_entry_assembly_required(self):
        self.manifest["EntryAssembly"] = "Missing.dll"
        with self.assertRaisesRegex(ValueError, "Build"):
            package(self.source, self.root / "out", self.manifest)


if __name__ == "__main__":
    unittest.main()
