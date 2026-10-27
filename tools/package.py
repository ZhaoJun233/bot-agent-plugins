"""Maintainer-side packaging only; never run this on a BotAgent installation."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from validate import ROOT, load_json, validate_archive, validate_manifest


def package(dll, output):
    manifest = load_json(ROOT / "examples/HelloPlugin/plugin.json")
    name = manifest["Id"] + "-" + manifest["Version"]
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (name + ".zip")
    info = zipfile.ZipInfo(manifest["EntryAssembly"], (2026, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.compress_type = zipfile.ZIP_STORED
    # A single explicit file is safer than recursively shipping an entire build output.
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(info, dll.read_bytes())
    manifest["Sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest["DownloadUrl"] = "https://github.com/ZhaoJun233/bot-agent-plugins/releases/download/" + name + "/" + archive.name
    validate_manifest(manifest)
    validate_archive(archive, manifest)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text(manifest["Sha256"] + "  " + archive.name + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", type=Path, default=ROOT / "examples/HelloPlugin/bin/Release/net8.0/HelloPlugin.dll")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/release")
    parser.add_argument("--write-catalog", action="store_true")
    args = parser.parse_args()
    manifest = package(args.dll, args.output)
    if args.write_catalog:
        location = ROOT / "plugins" / manifest["Id"] / manifest["Version"] / "manifest.json"
        if location.exists() and load_json(location) != manifest:
            raise ValueError("A published version is immutable; bump version instead")
        index_path = ROOT / "index.json"
        index = load_json(index_path) if index_path.exists() else {"SchemaVersion": 1, "Plugins": []}
        pins = [m for m in index["Plugins"] if (m["Id"], m["Version"]) == (manifest["Id"], manifest["Version"])]
        if pins and pins != [manifest]:
            raise ValueError("Catalog pin already exists with different bytes")
        if not pins:
            index["Plugins"].append(manifest)
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print("Packaged " + manifest["Id"] + " " + manifest["Version"] + " sha256=" + manifest["Sha256"])


if __name__ == "__main__":
    main()
