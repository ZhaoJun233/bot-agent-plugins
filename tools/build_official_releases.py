"""Maintainer tool: deterministically package all 13 official plugins-src/* bundles."""
import argparse
import shutil
import tempfile
from pathlib import Path

from package import package
from validate import ROOT, load_json


def build_all(output_dir, *, configuration="Release"):
    output_dir = Path(output_dir)
    plugins_root = ROOT / "plugins-src"
    if not plugins_root.is_dir():
        raise ValueError("plugins-src directory missing")
    results = []
    for pdir in sorted(plugins_root.iterdir(), key=lambda p: p.name):
        if not pdir.is_dir():
            continue
        tmpl_path = pdir / "manifest.template.json"
        if not tmpl_path.is_file():
            raise ValueError(f"Missing manifest.template.json in {pdir}")
        manifest = load_json(tmpl_path)
        tfm = manifest.get("TargetFramework", "net10.0")
        bin_dir = pdir / "backend" / "bin" / configuration / tfm
        if not bin_dir.is_dir():
            raise ValueError(f"Build output missing for {pdir.name}: {bin_dir}")
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            entry_src = bin_dir / manifest["EntryAssembly"]
            if not entry_src.is_file():
                raise ValueError(f"Entry assembly missing: {entry_src}")
            shutil.copy2(entry_src, stage / manifest["EntryAssembly"])
            for contract in manifest.get("SharedContracts") or []:
                dll_name = contract["Name"] + ".dll"
                contract_src = bin_dir / dll_name
                if not contract_src.is_file():
                    raise ValueError(f"Shared contract DLL missing: {contract_src}")
                shutil.copy2(contract_src, stage / dll_name)
            plugin_out = output_dir / manifest["Id"]
            archive, packaged = package(stage, plugin_out, manifest, web_root=pdir)
            results.append((archive, packaged))
    if not results:
        raise ValueError("No official plugin templates packaged")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "official-releases")
    parser.add_argument("--configuration", default="Release")
    args = parser.parse_args()
    results = build_all(args.output, configuration=args.configuration)
    for archive, manifest in results:
        print(f"PACKAGED: {manifest['Id']} {manifest['Version']} sha256={manifest['Sha256']} -> {archive}")
    print(f"Built and validated {len(results)} official plugin releases.")


if __name__ == "__main__":
    main()
