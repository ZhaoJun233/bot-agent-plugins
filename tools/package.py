"""Maintainer-only deterministic packager for prebuilt plugin assemblies.

Never builds or executes input. Contributor CI does not invoke this tool.
"""
import argparse
import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path

from validate import FORBIDDEN_ASSEMBLIES, MAX_UI_BYTES, ROOT, safe_path, validate_archive, validate_manifest


def package(source, output, manifest=None, *, sdk=None, web_root=None):
    if manifest is not None and manifest.get("ApiVersion") == 2:
        from package_python import package_python
        return package_python(source, output, manifest, sdk=sdk)
    source, output = Path(source), Path(output)
    if manifest is None:
        manifest = json.loads((ROOT / "plugins/community.example.hello/1.0.0/manifest.json").read_text())
    manifest = copy.deepcopy(manifest)
    if source.is_symlink():
        raise ValueError("Assembly input may not be a symbolic link")
    files = sorted(source.rglob("*.dll"), key=lambda p: p.relative_to(source).as_posix())
    if not files or len(files) > 2048:
        raise ValueError("Invalid assembly count")
    if not any(p.name == manifest["EntryAssembly"] for p in files):
        raise ValueError("Build the declared plugin before packaging")
    if any(p.name.lower() in FORBIDDEN_ASSEMBLIES for p in files):
        raise ValueError("Never redistribute host BotAgent.Core.dll or BotAgent.Plugin.Contracts.dll")
    if sum(p.stat().st_size for p in files) > 32 * 1024 * 1024:
        raise ValueError("Uncompressed assemblies exceed package budget")
    staged = []
    dll_hashes = {}
    for path in files:
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Assembly inputs may not contain symbolic links")
        rel = path.relative_to(source).as_posix()
        safe_path(rel)
        raw = path.read_bytes()
        staged.append((rel, raw))
        dll_hashes[rel.lower()] = hashlib.sha256(raw).hexdigest().lower()
    if manifest.get("SharedContracts"):
        contracts = []
        for contract in manifest["SharedContracts"]:
            item = dict(contract)
            key = item["Name"].lower() + ".dll"
            if key not in dll_hashes:
                raise ValueError("Missing SharedContract assembly: " + item["Name"])
            if item.get("Sha256") in (None, "", "0" * 64):
                item["Sha256"] = dll_hashes[key]
            contracts.append(item)
        manifest["SharedContracts"] = contracts
    if manifest.get("Ui"):
        ui = copy.deepcopy(manifest["Ui"])
        ui_base = Path(web_root) if web_root else source
        ui_total = 0
        new_assets = []
        for asset in ui["Assets"]:
            item = dict(asset)
            rel = item["Path"]
            safe_path(rel)
            asset_path = ui_base / rel
            if not asset_path.is_file() or any(p.is_symlink() for p in (asset_path, *asset_path.parents)):
                raise ValueError("Invalid UI asset file: " + rel)
            raw = asset_path.read_bytes()
            ui_total += len(raw)
            if ui_total > MAX_UI_BYTES:
                raise ValueError("UI bundle exceeds 4 MiB limit")
            if item.get("Sha256") in (None, "", "0" * 64):
                item["Sha256"] = hashlib.sha256(raw).hexdigest().lower()
            staged.append((rel, raw))
            new_assets.append(item)
        ui["Assets"] = sorted(new_assets, key=lambda a: a["Path"])
        manifest["Ui"] = ui
    staged.sort(key=lambda pair: pair[0])
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_STORED) as bundle:
        for rel, raw in staged:
            info = zipfile.ZipInfo(rel, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, raw)
    manifest["Sha256"] = hashlib.sha256(payload.getvalue()).hexdigest().lower()
    validate_manifest(manifest)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"{manifest['Id']}-{manifest['Version']}.zip"
    if archive.exists() and archive.read_bytes() != payload.getvalue():
        raise ValueError("An existing versioned ZIP is immutable; use a fresh staging directory or bump version")
    archive.write_bytes(payload.getvalue())
    validate_archive(archive, manifest)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text(manifest["Sha256"] + "  " + archive.name + "\n", encoding="utf-8")
    return archive, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "examples/HelloPlugin/bin/Release/net8.0")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/release")
    parser.add_argument("--manifest", type=Path, default=ROOT / "plugins/community.example.hello/1.0.0/manifest.json",
                        help="Manifest or canonical submission JSON; no code execution")
    parser.add_argument("--sdk", type=Path, help="Python only: canonical host botagent_worker.py (never fetched)")
    parser.add_argument("--check-catalog", action="store_true", help="Require exact submitted immutable ZIP hash")
    parser.add_argument("--write-catalog", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.write_catalog:
        parser.error("Direct catalog writes removed: submit canonical JSON, then run generate_catalog.py")
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    submitted = data.get("manifest", data)
    archive, manifest = package(args.input, args.output, submitted, sdk=args.sdk)
    if args.check_catalog and submitted["Sha256"] != manifest["Sha256"]:
        raise ValueError("Candidate ZIP differs from immutable submitted hash")
    print(archive)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
