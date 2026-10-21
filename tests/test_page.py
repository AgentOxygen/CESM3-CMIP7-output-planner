"""Drives the page script under node with a stubbed DOM (skipped where node is absent)."""
import json, shutil, subprocess
from pathlib import Path
import pytest

HARNESS = Path(__file__).parent / "page_harness.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


def run(exp="piControl"):
    return json.loads(subprocess.run(["node", str(HARNESS), exp], capture_output=True, text=True, check=True).stdout)


def test_tape_additions_in_both_configurations_chemistry_only_additions_need_mt4s():
    o = run()
    assert o["mtsoIcons"] > 0 and o["mt4sIcons"] > o["mtsoIcons"]
    assert o["mtso"]["atm"] > o["noExtra"]["atm"]                  # Simone's tape additions are on for MTso too
    assert o["mt4s"]["atm"] > o["mtso"]["atm"] and o["back"] == o["mtso"]   # MTt4s adds the chemistry-only ones
    assert o["chemOptHidden"] is False and o["chemOptHiddenAgain"] is True and o["addAtmDisabled"] is False
    for c in ("lnd", "ocn", "ice", "rof", "glc"):
        assert o["mt4s"][c] == o["mtso"][c] == o["noExtra"][c]     # the additions are all CAM fields


def test_additional_checkbox_is_inclusive_and_group_checkboxes():
    o = run()
    assert o["onlyAllExtra"] and o["only"]["atm"] == o["onlyIcons"] > 0 and sum(o["only"].values()) == o["only"]["atm"]
    assert o["only"]["atm"] == o["mt4s"]["atm"] - o["noExtra"]["atm"]     # no mapping box ticked = just the additions
    # each group checkbox removes only its own group: chemistry-only + simone-tapes = all additions
    assert 0 < o["noChem"]["atm"] < o["only"]["atm"] and 0 < o["noAtm"]["atm"] < o["only"]["atm"]
    assert o["noChem"]["atm"] + o["noAtm"]["atm"] == o["only"]["atm"]


def test_namelist_with_additions_has_a_5day_tape_and_validates():
    nl = run()["nl"]
    assert "error" not in nl and "5day" in nl["freqs"] and nl["errors"] == []
