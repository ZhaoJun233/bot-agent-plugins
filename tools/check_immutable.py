"""Reject edits/removals of already published release pins in a PR or push."""
import os
import subprocess

from validate import ROOT, load_json


def main():
    base = os.environ.get("BASE_SHA", "")
    if not base or set(base) == {"0"}:
        print("Initial snapshot: no previous release pins")
        return
    import json
    result = subprocess.run(["git", "show", base + ":index.json"], cwd=ROOT,
                            text=True, capture_output=True, check=True)
    old = json.loads(result.stdout)
    current = load_json(ROOT / "index.json")
    by_pin = {(m["Id"], m["Version"]): m for m in current["Plugins"]}
    for manifest in old["Plugins"]:
        if by_pin.get((manifest["Id"], manifest["Version"])) != manifest:
            raise ValueError("Existing release pins cannot be modified or removed; publish a new version")
    print("PASS: existing release pins unchanged")


if __name__ == "__main__":
    main()
