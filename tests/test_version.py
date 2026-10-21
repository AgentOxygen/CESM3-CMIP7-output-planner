"""tools/stamp_version.py and the committed docs/version.json."""
import json, re, shutil, subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_committed_stamp_is_well_formed():
    v = json.loads((ROOT / "docs" / "version.json").read_text())
    assert re.fullmatch(r"[0-9a-f]{40}", v["commit"]) and v["short"].startswith(v["commit"][:7])
    assert v["repo"] is None or v["repo"].startswith("https://github.com/")


@pytest.mark.skipif(not shutil.which("git") or subprocess.run(["git", "-C", str(ROOT), "rev-parse"], capture_output=True).returncode,
                    reason="needs git and a checkout (the dev container has neither)")
def test_stamp_names_head():
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from stamp_version import stamp
    s = stamp()
    assert s["commit"] == subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
