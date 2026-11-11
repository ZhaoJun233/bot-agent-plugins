"""Exercise reviewed example ZIPs with the canonical protocol-v1 SDK; synthetic data only."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def require(condition, label):
    if not condition:
        raise AssertionError(label)


def probe(release, sdk):
    manifest = json.loads((release / "manifest.json").read_bytes())
    version = manifest["Version"]
    require(manifest["Id"] == "community.example.python-echo" and manifest["ApiVersion"] == 2, "example identity")
    require(manifest["Permissions"] == [] and manifest["Dependencies"] == [], "empty authority declarations")
    archive = release / (manifest["Id"] + "-" + version + ".zip")
    require(hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["Sha256"], "exact ZIP pin")
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        require(len(names) == 2 and set(names) == {"worker.py", "botagent_worker.py"}, "minimal package contents")
        worker = bundle.read("worker.py")
        canonical = bundle.read("botagent_worker.py")
    require(canonical == sdk.read_bytes(), "canonical host SDK raw bytes")
    methods = [
        ("tools/list", {}),
        ("initialize", {"protocolVersion": 1, "configuration": {"prefix": "synthetic-prefix"}, "capabilities": []}),
        ("tools/list", {}),
        ("tools/call", {"name": "echo", "arguments": {"text": "synthetic-text"}}),
        ("tools/call", {"name": "echo", "arguments": {"text": "x" * 201}}),
        ("tools/call", {"name": "echo", "arguments": {"text": "synthetic-text", "unexpected": True}}),
        ("tools/call", {"name": "hidden", "arguments": {}}),
        ("shutdown", {}),
    ]
    frames = "".join(json.dumps({"jsonrpc": "2.0", "id": number, "method": method, "params": parameters}) + "\n"
                     for number, (method, parameters) in enumerate(methods, 1))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "worker.py").write_bytes(worker)
        (root / "botagent_worker.py").write_bytes(canonical)
        environment = {name: os.environ[name] for name in ("PATH", "SystemRoot", "SYSTEMROOT") if name in os.environ}
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run([sys.executable, "-B", str(root / "worker.py")], cwd=root,
                                input=frames.encode("utf-8"), capture_output=True, timeout=10, env=environment)
    require(result.returncode == 0 and not result.stderr, "clean bounded worker shutdown")
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    require([row.get("id") for row in responses] == list(range(1, 9)), "exact frame correlation")
    require(all(row.get("jsonrpc") == "2.0" for row in responses), "protocol envelope")
    require(responses[0]["error"]["message"] == "worker_request_failed", "discovery before initialization rejected")
    require(responses[1]["result"] == {"protocolVersion": 1}, "protocol initialization")
    tools = responses[2]["result"]["tools"]
    require(len(tools) == 1 and tools[0]["name"] == "echo", "one declared tool only")
    require(tools[0]["annotations"] == {"readOnlyHint": True}, "readonly metadata")
    echo = responses[3]["result"]
    require(echo["isError"] is False and json.loads(echo["content"]) ==
            {"text": "synthetic-text", "prefix": "synthetic-prefix", "version": version}, "version and configuration contract")
    require(all(responses[number]["result"] == {"content": "", "isError": True} for number in (4, 5)), "bounded exact argument schema")
    require(responses[6]["error"]["message"] == "worker_request_failed", "undeclared tool rejected")
    require(responses[7]["result"] == {}, "shutdown response")
    return version, manifest["Sha256"], hashlib.sha256(worker).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("releases", nargs=2, type=Path)
    arguments = parser.parse_args()
    results = [probe(release, arguments.sdk) for release in arguments.releases]
    require({row[0] for row in results} == {"1.0.0", "1.0.1"}, "both real versions")
    require(len({row[1] for row in results}) == 2 and len({row[2] for row in results}) == 2, "distinct ZIP and worker bytes")
    print(json.dumps({"versions": sorted(row[0] for row in results), "protocol_cases": 16,
                      "canonical_sdk": True, "distinct_worker_bytes": True, "native_exit": 0}))


if __name__ == "__main__":
    main()
