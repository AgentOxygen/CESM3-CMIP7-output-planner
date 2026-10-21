"""Drives the page script under node with a stubbed DOM (skipped where node is absent)."""
import json, re, shutil, subprocess
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


def test_volume_charts_button_toggles_the_charts_panel():
    o = run()
    assert o["pies"] == 2                                          # both pies are drawn into #charts
    assert o["chartsOpen"]["hidden"] is False and o["chartsOpen"]["aria"] == "true" and "Hide" in o["chartsOpen"]["text"]
    assert o["chartsShut"]["hidden"] is True and o["chartsShut"]["aria"] == "false" and "Show" in o["chartsShut"]["text"]


def test_elements_that_start_hidden_can_actually_hide():
    # A class rule such as `.charts { display: flex }` beats the hidden attribute, so each id needs its own [hidden] rule.
    html = (Path(__file__).parent.parent / "docs" / "index.html").read_text()
    ids = re.findall(r'<\w+[^>]*\bid="(\w+)"[^>]*\shidden\b|<\w+[^>]*\shidden\b[^>]*\bid="(\w+)"', html)
    ids = {a or b for a, b in ids}
    assert {"charts", "info", "filters", "chemOpt"} <= ids
    for i in ids:
        assert re.search(rf"#{i}\[hidden\]\s*\{{\s*display:\s*none", html), f"#{i}[hidden] has no display:none rule"


def test_component_checkbox_drops_a_whole_namelist_from_total_charts_and_zip():
    o = run()
    a, no_atm, none, back = o["compAll"], o["compNoAtm"], o["compNone"], o["compBack"]
    assert a["boxes"] == a["checked"] > 1                          # one checkbox per listed component, all on by default
    assert no_atm["boxes"] == a["boxes"] and no_atm["checked"] == a["checked"] - 1 and o["compNoAtmHtml"]
    assert float(no_atm["tot"].replace(",", "")) < float(a["tot"].replace(",", ""))    # atm's volume leaves the total
    assert "atm" in a["charts"] and "atm" not in no_atm["charts"]  # ...and the component pie
    assert no_atm["zipDisabled"] is False                          # other components still download
    assert none["checked"] == 0 and none["zipDisabled"] is True and none["tot"] == "0"
    assert back == a                                               # re-enabling restores everything


def test_clean_namelist_shows_no_status_but_errors_still_do():
    o = run()
    assert o["cleanStatus"] is False and o["errorStatus"] is True


def test_realms_and_frequencies_button_toggles_and_summarises():
    o = run()
    assert o["rfOpen"]["hidden"] is False and o["rfOpen"]["aria"] == "true" and "Hide" in o["rfOpen"]["text"]
    assert o["rfShut"]["hidden"] is True and o["rfShut"]["aria"] == "false" and "Show" in o["rfShut"]["text"]
    assert o["rfNoteAll"] == "all shown" and o["rfNoteOff"] == "1 realm(s) and 2 frequencies turned off"


def test_namelist_options_button_and_empty_htapes_checkboxes():
    o = run()
    assert o["nlOpen"]["hidden"] is False and o["nlOpen"]["aria"] == "true" and "Hide" in o["nlOpen"]["text"]
    assert o["nlShut"]["hidden"] is True and o["nlShut"]["aria"] == "false" and "Show" in o["nlShut"]["text"]
    assert o["emptyBoxes"] == ["atm", "lnd"]                      # only the components whose namelist has such a switch
    assert o["emptyOn"] is True and o["nlNoteAll"] == ""          # default: on, as before
    assert o["emptyOff"] is False and o["nlNoteOff"] == "default output kept for atm"


def test_planner_version_is_linked_on_the_page_and_written_into_namelists():
    o = run()
    v = json.loads((Path(__file__).parent.parent / "docs" / "version.json").read_text())
    assert f"/commit/{v['commit']}" in o["plannerSrc"] and v["short"] in o["plannerSrc"]
    assert f"! Planner version: {v['short']}\n!   {v['repo']}/commit/{v['commit']}\n" in o["versionInNamelist"]
