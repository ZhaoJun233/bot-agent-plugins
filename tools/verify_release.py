"""Offline fixed-asset verification; does not upload, download, or execute ZIPs."""
import argparse
from pathlib import Path

from generate_catalog import document
from validate import validate_archive
from validate_python import validate_python_archive


def verify_release(manifest_path, before, after=None):
    data = document(manifest_path)
    manifest = data.get("manifest", data)
    for archive in (before, after):
        if archive is not None:
            archive = Path(archive)
            if any(p.is_symlink() for p in (archive, *archive.parents)):
                raise ValueError("Release artifact may not be a symbolic link")
            validator = validate_python_archive if manifest.get("ApiVersion") == 2 else validate_archive
            validator(archive, manifest)
    return manifest["Id"], manifest["Version"], manifest["Sha256"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True, help="Pre-upload fixed ZIP")
    parser.add_argument("--after", type=Path, help="Separately obtained post-publication ZIP; never downloaded here")
    args = parser.parse_args()
    identity = verify_release(args.manifest, args.before, args.after)
    print("Fixed asset OK: %s %s sha256=%s; layout/hash only, no code execution" % identity)
    if args.after is None:
        print("No post-publication copy supplied; live publication NOT verified")


if __name__ == "__main__":
    main()
