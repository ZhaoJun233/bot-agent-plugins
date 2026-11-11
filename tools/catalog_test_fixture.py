"""Fixed first-wave inputs for single-version catalog contract tests."""
import json
import shutil
import tempfile
from pathlib import Path

from generate_catalog import ROOT, synchronize


def first_wave_catalog(test_case):
    temporary = tempfile.TemporaryDirectory()
    test_case.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    shutil.copytree(ROOT / "catalog", root / "catalog")
    submission = Path("submissions/community.example.hello/1.0.0.json")
    (root / submission).parent.mkdir(parents=True)
    shutil.copy2(ROOT / submission, root / submission)
    ledger = root / "governance/ledger.json"
    ledger.parent.mkdir()
    ledger.write_text(json.dumps({"schemaVersion": 1,
                                "generatedAt": "2026-11-06T00:00:00Z",
                                "entries": []}), encoding="utf-8")
    synchronize(root)
    return root
