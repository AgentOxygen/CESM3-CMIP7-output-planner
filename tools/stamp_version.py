#!/usr/bin/env python3
"""Write docs/version.json: the git commit this checkout is built on, for the page and the generated namelists.

Run on the host (the dev container has no git):  make stamp

The stamp can only name the commit it was made on top of, never the commit that contains it, so a
committed version.json points at its parent. "-dirty" means uncommitted changes (version.json aside).
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "version.json"


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()


def stamp():
    full = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--", ".", ":!docs/version.json"))
    m = re.match(r"(?:git@github\.com:|https://github\.com/)(.+?)(?:\.git)?$", git("remote", "get-url", "origin"))
    return {"commit": full, "short": full[:7] + ("-dirty" if dirty else ""),
            "repo": f"https://github.com/{m.group(1)}" if m else None}


if __name__ == "__main__":
    OUT.write_text(json.dumps(stamp(), indent=1) + "\n")
    print(f"{OUT.relative_to(ROOT)}: {json.loads(OUT.read_text())['short']}")
