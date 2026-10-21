"""Drives docs/namelist.js under node (skipped where node is absent)."""
import json, shutil, subprocess
from pathlib import Path
import pytest

JS = Path(__file__).resolve().parents[1] / "docs" / "namelist.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


def build(comp, rows, meta=None):
    rows = [{"items": [], "method": None, **r} for r in rows]
    code = f"console.log(JSON.stringify(require({json.dumps(str(JS))}).build({json.dumps(comp)}, {json.dumps(rows)}, {json.dumps(meta or {})})))"
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


def test_cam_tapes_ordered_and_flagged():
    out = build("atm", [{"name": "T", "freq": "day", "method": "A"},
                        {"name": "PRECT", "freq": "mon", "method": "A"},
                        {"name": "TREFHTMX", "freq": "day", "method": "X"}])
    t = out["text"]
    assert " empty_htapes = .true." in t and " nhtfrq = 0, -24\n" in t and " mfilt = 1, 30\n" in t
    assert " fincl1 = 'PRECT:A'\n" in t
    assert " fincl2 = 'T:A','TREFHTMX:X'\n" in t


def test_same_name_two_methods_split_tapes():
    out = build("atm", [{"name": "T", "freq": "day", "method": "A"}, {"name": "T", "freq": "day", "method": "X"}])
    assert len(out["tapes"]) == 2 and " nhtfrq = -24, -24\n" in out["text"]


def test_ctsm_prefix_sum_and_dov2xy():
    out = build("lnd", [{"name": "QFLX", "freq": "mon", "method": "SUM"}])
    t = out["text"]
    assert " hist_empty_htapes = .true." in t and " hist_dov2xy = .true.\n" in t and " hist_fincl1 = 'QFLX:SUM'\n" in t


def test_dropped_not_exported():
    out = build("atm", [{"name": "T", "freq": "mon", "method": "SUM"},        # SUM invalid in CAM
                        {"name": "X" * 33, "freq": "mon"},                    # too long
                        {"name": "AREA", "freq": "fx"}])                      # no history setting
    assert len(out["dropped"]) == 3 and "(nothing to export)" in out["text"]


def test_tape_budget_refused():
    rows = [{"name": "T", "freq": "mon", "method": m} for m in "AIMXBLNS"] + \
           [{"name": "T", "freq": "day", "method": m} for m in "AIM"]
    assert "allows 10" in build("atm", rows)["error"]


def test_header_carries_generation_date():
    import re
    assert re.match(r"! Generated \d{4}-\d{2}-\d{2} by the CESM3-CMIP7-output-planner", build("atm", [])["text"])


def run(expr):
    code = f"const N=require({json.dumps(str(JS))}); console.log(JSON.stringify({expr}))"
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


def test_mosart_additive_and_three_tape_limit():
    out = build("rof", [{"name": "RIVER_DISCHARGE_OVER_LAND_LIQ", "freq": "day", "method": "A"}])
    assert "ADDED to the model's default" in out["text"] and "empty_htapes = .true." not in out["text"]
    assert " fincl1 = 'RIVER_DISCHARGE_OVER_LAND_LIQ:A'\n" in out["text"]
    many = [{"name": "Q", "freq": f} for f in ("mon", "day", "6hr", "3hr")]
    assert "allows 3" in build("rof", many)["error"]


def test_cism_coarsest_default_and_variants():
    out = build("glc", [{"name": "thk", "freq": "yr"}, {"name": "topg", "freq": "dec"}, {"name": "smb", "freq": "mon"}])
    assert " esm_history_vars = 'topg'\n" in out["text"] and " history_frequency = 10\n" in out["text"]
    assert [v["freq"] for v in out["variants"]] == ["yr"] and " esm_history_vars = 'thk'\n" in out["variants"][0]["text"]
    assert [d["name"] for d in out["dropped"]] == ["smb"]            # monthly is not expressible


def test_zip_is_valid_and_round_trips(tmp_path):
    files = [{"name": "user_nl_cam", "text": "a = 1\n"}, {"name": "variants/x", "text": "é\n"}]
    data = bytes(run(f"Array.from(N.zip({json.dumps(files)}))"))
    import zipfile, io
    z = zipfile.ZipFile(io.BytesIO(data))
    assert z.testzip() is None and z.namelist() == ["user_nl_cam", "variants/x"]
    assert z.read("variants/x").decode() == "é\n"


ICE = ["aice", "siage", "sidconcdyn"]


def build_ice(rows):
    code = f"console.log(JSON.stringify(require({json.dumps(str(JS))}).build('ice', {json.dumps([{'items': [], 'method': None, **r} for r in rows])}, {{iceFields: {json.dumps(ICE)}}})))"
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


def test_cice_masks_streams_and_alias():
    t = build_ice([{"name": "aice", "freq": "mon"}, {"name": "aice", "freq": "day"}, {"name": "siage_d", "freq": "day"},
                   {"name": "nonsense", "freq": "mon"}])["text"]
    assert " histfreq = 'm', 'd', 'x', 'x', 'x'\n" in t and " histfreq_n = 1, 1, 0, 0, 0\n" in t
    assert " f_aice = 'md'\n" in t and " f_siage = 'd'\n" in t
    assert "no f_ switch of that name in CICE: 1" in t and "nonsense (mon)" in t


def test_cice_shared_letter_drops_finer_stream():
    out = build_ice([{"name": "aice", "freq": "6hr"}, {"name": "siage", "freq": "1hr"}])
    assert " histfreq = 'h', 'x'" in out["text"] and " histfreq_n = 6, 0" in out["text"]
    assert [d["name"] for d in out["dropped"]] == ["siage"]


def test_mom6_diag_table_modules_reductions_and_aliases():
    rows = [{"items": [], "method": m, "name": n, "freq": f} for n, f, m in
            [("thetao", "mon", "A"), ("tos", "mon", "A"), ("tos", "mon", "X"), ("so", "day", "I"), ("mystery", "mon", "A")]]
    meta = {"momFields": {"ocean_model": ["tos"], "ocean_model_z": ["thetao", "so"]}}
    code = f"console.log(JSON.stringify(require({json.dumps(str(JS))}).build('ocn', {json.dumps(rows)}, {json.dumps(meta)})))"
    import re
    t = re.sub(r" +", " ", json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)["text"])
    assert '"ocean_model_z", "thetao", "thetao", "${CASE}.mom6.h.mon.z.%4yr-%2mo", "all", "mean", "none", 2' in t
    assert '"ocean_model", "tos", "tos_max", "${CASE}.mom6.h.mon.native.%4yr-%2mo", "all", "max", "none", 2' in t
    assert '"ocean_model_z", "so", "so_inst"' in t and '"ocean_model", "mystery", "mystery"' in t
    assert '"${CASE}.mom6.h.day.z.%4yr-%2mo", 1, "days", 1, "days", "time", 1, "months"' in t


def test_header_reports_source_only_and_unevidenced_lines():
    code = (f"console.log(JSON.stringify(require({json.dumps(str(JS))}).build('atm', "
            f"[{{name:'T',freq:'mon',method:'A',items:[]}}], {{unverified: 2, sourceOnly: 5, sourceConfiguration: 'CFG'}})))")
    t = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)["text"]
    assert "2 line(s) have no CESM3 source or run-log evidence" in t
    assert "5 line(s) are registered by the CESM3 source for CFG but were not seen in a run log" in t


def test_cam_lists_wrap_under_the_line_limit():
    rows = [{"name": f"FIELD_{i:03d}", "freq": "mon", "method": "A"} for i in range(200)]
    out = build("atm", rows)
    assert all(len(l) <= 100 for l in out["text"].split("\n")) and out["validation"]["errors"] == []
    assert out["text"].count("'FIELD_") == 200


def test_dropped_and_unevidenced_names_go_in_a_trailing_block():
    rows = [{"name": "T", "freq": "mon", "method": "A"}, {"name": "AREA", "freq": "fx"},
            {"name": "ODDBALL", "freq": "mon", "method": "A", "items": [{"t": {"st": "spreadsheet-only"}}]}]
    t = build("atm", rows)["text"]
    assert t.index(" fincl1 = ") < t.index("--- not exported: 1 line(s)") < t.index("--- no CESM3 source or run-log evidence (1)")
    assert "frequency fx has no history setting: 1" in t


def test_validate_catches_a_bad_namelist():
    rows = [{"name": "T", "freq": "mon", "method": "A"}, {"name": "Q", "freq": "mon", "method": "A"}]
    good = build("atm", rows)
    assert good["validation"] == {"errors": [], "warnings": []}
    bad = good["text"].replace("'Q:A'", "'T:A'").replace("nhtfrq = 0", "nhtfrq = 0, -24")
    code = f"console.log(JSON.stringify(require({json.dumps(str(JS))}).validate('atm', {json.dumps(bad)}, {json.dumps(rows)}, [])))"
    errs = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)["errors"]
    assert any("appears twice" in e for e in errs) and any("nhtfrq lists 2" in e for e in errs)
    assert any("requested but missing" in e and "Q A mon" in e for e in errs)


def test_validation_findings_are_written_into_the_file():
    # a CICE field the page does not know is dropped, so the file stays valid; a name not in iceFields in the text is an error
    out = build_ice([{"name": "aice", "freq": "mon"}])
    assert out["validation"]["errors"] == [] and "VALIDATION" not in out["text"]


# --- real combinations: the committed docs/data.json, selected the way the page does ----------------------------

DATA = JS.parent / "data.json"

REAL = r"""
const B = require(%(data)s), N = require(%(js)s);
const out = [];
for (const [exp, only] of %(cases)s) {
  const comps = {};
  for (const c of B.components) comps[c] = new Map();
  for (const i of B.experiments[exp]) {
    const r = B.requests[i];
    if (only && r.f !== only) continue;
    for (const t of r.t) {
      if (!["verified", "source"].includes(t.st)) continue;       // the page's default statuses
      const k = t.n + "|" + (t.m || "") + "|" + r.f;
      if (!comps[t.c].has(k)) comps[t.c].set(k, { name: t.n, method: t.m, freq: r.f, items: [] });
      comps[t.c].get(k).items.push({ r, t });
    }
  }
  for (const c of Object.keys(N.COMPONENTS)) {
    const rows = [...comps[c].values()];
    if (!rows.length) continue;
    const meta = { iceFields: B.cice_fields, momFields: B.mom_fields, title: "experiment " + exp,
      unverified: rows.filter(r => r.items.some(x => !["verified", "source"].includes(x.t.st))).length,
      sourceOnly: rows.filter(r => r.items.some(x => x.t.st === "source")).length, sourceConfiguration: B.source_configuration };
    const o = N.build(c, rows, meta);
    out.push({ exp, only, comp: c, rows: rows.length, error: o.error || null, text: o.text || "", errors: o.validation ? o.validation.errors : [],
               dropped: (o.dropped || []).length });
  }
}
console.log(JSON.stringify(out));
"""


def real(cases):
    code = REAL % {"data": json.dumps(str(DATA)), "js": json.dumps(str(JS)), "cases": json.dumps(cases)}
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


FREQS = [None, "mon", "day", "6hr", "3hr", "1hr", "yr", "dec"]


def test_real_experiments_validate_and_wrap_for_every_frequency():
    cases = [[e, f] for e in ("piControl", "historical", "esm-hist", "scen7-m") for f in FREQS]
    results = real(cases)
    assert results
    for r in results:
        where = f"{r['exp']} / {r['only'] or 'all frequencies'} / {r['comp']}"
        if r["error"]:
            assert "history tapes" in r["error"], where           # only the tape budget may refuse a selection
            continue
        assert r["errors"] == [], where
        for n, line in enumerate(r["text"].split("\n"), 1):
            is_comment = line.startswith(("!", "#"))
            if is_comment:
                assert len(line) <= 100, f"{where}: comment line {n} is {len(line)} wide"
            elif r["comp"] != "ocn":                              # the diag_table is not a Fortran namelist
                assert len(line) <= 132, f"{where}: line {n} is {len(line)} wide"
            if r["comp"] in ("atm", "lnd", "rof") and "fincl" in line or line.startswith("    '"):
                assert len(line) <= 100, f"{where}: list line {n} is {len(line)} wide"


def test_picontrol_three_hourly_atm_header_is_wrapped():
    (r,) = [x for x in real([["piControl", "3hr"]]) if x["comp"] == "atm"]
    lines = r["text"].split("\n")
    assert r["errors"] == [] and max(len(l) for l in lines) <= 100
    i = next(n for n, l in enumerate(lines) if "were not seen in a run" in l)
    assert lines[i + 1].startswith("!   ") and "may not exist in every case" in lines[i + 1]
    assert " nhtfrq = -3" in r["text"] and " mfilt = 240" in r["text"]
    assert r["text"].count("fincl1 = ") == 1


def test_empty_htapes_can_be_left_at_its_default_per_component():
    rows = [{"name": "T", "freq": "day", "method": "A"}]
    for comp, key in (("atm", "empty_htapes"), ("lnd", "hist_empty_htapes")):
        on = build(comp, rows)
        assert f" {key} = .true." in on["text"] and on["validation"]["errors"] == []
        off = build(comp, rows, {"emptyOff": [comp]})
        assert f" {key} = .true." not in off["text"] and "left at its default" in off["text"]
        assert off["validation"]["errors"] == []                  # leaving it out is not an error
        # opting out one component does not touch the other
        other, okey = ("lnd", "hist_empty_htapes") if comp == "atm" else ("atm", "empty_htapes")
        assert f" {okey} = .true." in build(other, rows, {"emptyOff": [comp]})["text"]
