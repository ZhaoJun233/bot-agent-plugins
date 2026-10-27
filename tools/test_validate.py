import copy
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from jsonschema import ValidationError
from validate import ROOT, load_json, safe_path, validate_archive, validate_index, validate_manifest


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_json(ROOT / "artifacts/release/manifest.json")

    def reject(self, key, value):
        manifest = copy.deepcopy(self.manifest)
        manifest[key] = value
        with self.assertRaises((ValueError, ValidationError)):
            validate_manifest(manifest)

    def test_valid_manifest(self):
        validate_manifest(self.manifest)

    def test_invalid_pins(self):
        for key, value in [("Version", "latest"), ("Version", "1.0.0+local"),
                           ("Version", "1.0.0-01"), ("Version", "1.0.0-alpha--beta"), ("ApiVersion", 2),
                           ("Sha256", "0" * 64), ("Sha256", "bad"),
                           ("Id", "preset.feature.test"), ("Id", "test..bad"),
                           ("Id", "con"), ("TargetFramework", "net9.0"),
                           ("Permissions", ["*"]), ("EntryAssembly", "../Bad.dll"),
                           ("Extra", "unknown")]:
            with self.subTest(key=key, value=value):
                self.reject(key, value)

    def test_release_link(self):
        for url in ["http://example.com/plugin.zip", "https://github.com/a/b/releases/latest/download/plugin.zip",
                    self.manifest["DownloadUrl"] + "?token=placeholder"]:
            self.reject("DownloadUrl", url)

    def test_settings(self):
        for setting in [{"Key": "token", "Label": "Token", "Type": "secret", "DefaultValue": "placeholder"},
                        {"Key": "choice", "Label": "Choice", "Type": "select", "Choices": []},
                        {"Key": "flag", "Label": "Flag", "Type": "boolean", "DefaultValue": "yes"},
                        {"Key": "count", "Label": "Count", "Type": "number", "DefaultValue": "NaN"}]:
            self.reject("Settings", [setting])

    def test_duplicate_settings(self):
        item = {"Key": "same", "Label": "Same", "Type": "string"}
        self.reject("Settings", [item, item])

    def test_dependencies(self):
        self.reject("Dependencies", [{"Id": self.manifest["Id"], "Version": "1.0.0"}])
        item = {"Id": "community.other", "Version": "1.0.0"}
        self.reject("Dependencies", [item, item])
        other = copy.deepcopy(self.manifest)
        other["Dependencies"] = [item]
        with self.assertRaises(ValueError):
            validate_index({"SchemaVersion": 1, "Plugins": [other]})

    def test_duplicate_release(self):
        with self.assertRaises(ValueError):
            validate_index({"SchemaVersion": 1, "Plugins": [self.manifest, self.manifest]})

    def test_paths(self):
        for name in ["../Bad.dll", "/Bad.dll", "a\\Bad.dll", "con.dll", "x/aux.dll", "x//bad.dll", "x:bad.dll", "x./bad.dll"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_path(name)

    def test_archive_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.zip"
            path.write_bytes(b"not an archive")
            with self.assertRaises(ValueError):
                validate_archive(path, self.manifest)

    def test_forbidden_archive_entries(self):
        for filename in ["install.sh", "Plugin.cs", "BotAgent.Core.dll", "../bad.dll"]:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bad.zip"
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(filename, b"MZfake")
                manifest = copy.deepcopy(self.manifest)
                manifest["Sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaises(ValueError):
                    validate_archive(path, manifest)


if __name__ == "__main__":
    unittest.main()
