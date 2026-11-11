"""Explicit maintainer-only native smoke for the trusted synthetic Python example.

Never invoked by contributor CI. This deliberately executes the reviewed example.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from generate_catalog import document
from validate_python import validate_python_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sdk-sha256", required=True)
    args = parser.parse_args()
    manifest = document(args.manifest)
    validate_python_archive(args.archive, manifest)
    with tempfile.TemporaryDirectory() as temp:
        with zipfile.ZipFile(args.archive) as bundle:
            if hashlib.sha256(bundle.read("botagent_worker.py")).hexdigest() != args.sdk_sha256:
                raise ValueError("SDK does not match the reviewed host candidate")
            bundle.extractall(temp)  # Paths and duplicate entries validated above.
        frames = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1, "configuration": {"prefix": "synthetic"}, "capabilities": []}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "synthetic echo"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": 5}}},
            {"jsonrpc": "2.0", "id": 5, "method": "shutdown", "params": {}},
        ]
        env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
        bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv[1]);runpy.run_path(sys.argv[2],run_name='__main__')"
        completed = subprocess.run([sys.executable, "-I", "-u", "-c", bootstrap, temp,
                                    str(Path(temp) / manifest["Runtime"]["EntryPoint"])],
                                   input="\n".join(json.dumps(frame) for frame in frames) + "\n",
                                   text=True, encoding="utf-8", capture_output=True, timeout=15, env=env, cwd=temp)
        if completed.returncode != 0 or completed.stderr:
            raise ValueError("Native synthetic worker failed; output deliberately suppressed")
        results = [json.loads(line) for line in completed.stdout.splitlines()]
        assert [result["id"] for result in results] == [1, 2, 3, 4, 5]
        assert results[0]["result"] == {"protocolVersion": 1}
        assert [tool["name"] for tool in results[1]["result"]["tools"]] == ["echo"]
        assert json.loads(results[2]["result"]["content"]) == {"text": "synthetic echo", "prefix": "synthetic"}
        assert results[3]["result"] == {"content": "", "isError": True}
        assert results[4]["result"] == {}
    print(json.dumps({"status": "pass", "assertions": 6, "frames": 5,
                      "archiveSha256": manifest["Sha256"], "sdkSha256": args.sdk_sha256,
                      "python": ".".join(str(v) for v in sys.version_info[:3]),
                      "scope": "trusted local synthetic worker only; not host integration/publication/sandbox proof"}))

if __name__ == "__main__":
    main()
