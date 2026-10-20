# CESM3-CMIP7-output-planner

CMIP7 → CESM3 variable lists: plan which history output a CESM3 run needs to satisfy the
CMIP7 data request, per component, with namelists and a rough data-volume estimate.

A scientist is handed the full CMIP7 data request and has to work out which
CESM3 history variables to put in each component's namelist. This tool answers,
in order:

1. **Which variables does my experiment need?** Pick an experiment (and a
   priority cutoff) to get the matching CMIP7 compound names.
2. **Which CESM3 variables is that, by model component?** Each component
   (atm, lnd, ocn, ice, rof, glc) needs its own namelist.
3. **At which frequencies?** Every frequency needs its own entry, even for the
   same variable.
4. **Save the list.** One plain-text file per component, one `VARIABLE
   FREQUENCY` line each. Namelist formatting is a later step.

It is a static page (no server), published from `docs/` via GitHub Pages.

## Reading the mapping

The CMIP7 → CESM3 mapping comes from a spreadsheet, and it is not equally
trustworthy everywhere. Every variable shows how its mapping was derived, so the
page can be audited against the source data:

| Symbol | Status | Meaning |
|---|---|---|
| ✓ | verified | named in the spreadsheet (`CESM3_current_v2.csv`) **and** registered by a real CESM3 run's log, in a component that run configures like the baseline (lnd, ice, ocn, rof; see below) |
| ● | in CESM3 source | not verified, but the CESM3 source (`cesm3_0_alpha11d`) registers it for the baseline configuration (BHISTE_MTt4s_alpha11d); the audit view says whether by a literal name, as one name of a loop, or only as a runtime-built pattern, and cites the file and line |
| ◐ | spreadsheet only | named in the spreadsheet, in neither a log nor the source |
| ⚠ | missing | the spreadsheet row gives no CESM variable name (listed, never exported) |

A second marker says where the **component** came from: the run `log`, the CESM3
`source`, or a `realm` guess from the CMIP7 realm column
(`REALM_FALLBACK` in `tools/import_cmip7.py`). `≠realm` flags a variable the
log put in a different component than its realm implies.

**The run log is not a T4S run.** The only log is an MTso run (`ghg_mam4` chemistry,
cesm3_0_alpha09e, evolving Greenland ice sheet); the spreadsheet and the baseline are T4S. So
the log verifies only CTSM, CICE, MOM6 and MOSART fields (`LOG_VERIFIES` in
`tools/import_cmip7.py`): in atm it still says which component a name lives in, but the
status comes from the T4S source, and no atm or glc field is `✓`.

**Time methods.** CMIP7 asks for means, instantaneous values, maxima and minima
of the same field, and CESM writes each as a separate output. The method comes
from the compound name (`tavg` → `A`, `tpt` → `I`, `tmax` → `X`, `tmin` → `M`,
`tsum` → `SUM`; `TIME_METHODS` in `tools/import_cmip7.py`), unless the
spreadsheet's CESM name carries its own suffix (`O3:i`). Lines are
`NAME:FLAG freq` for atm and lnd, whose namelists take that suffix; ice, ocn, rof
and glc get the plain name with the method as a trailing comment, because their
time methods are set elsewhere. Climatology, diurnal-cycle and monthly-mean-of-daily-extreme
requests (`tclm`, `tclmdc`, `tmaxavg`, `tminavg`) are written as the nearest
direct flag with a post-processing caveat shown in the audit view.

Click any row for its audit trail: the raw spreadsheet cell, UID, CSV line,
priority groups and the logs involved. Each component's **csv** carries
the same trail for every exported line; **raw_text** itself holds CESM3 names
only, never compound names.

## How the data is made

```
reference/CESM3_current_v2.csv         the CMIP7 request joined to CESM variable names (T4S)
reference/cmip7-data-request/*.csv     priority levels, variable groups
reference/log_files/                   real CESM3 run logs
        │  tools/extract_log_fields.py   → reference/log_files/extracted_fields.yaml
cesm-field-scraper/out-alpha11d/       the CESM3 source catalogue (cesm-field-scraper; local-only)
        │  tools/import_cmip7.py         (make import-cmip7)
        ▼
data/cmip7_request.yaml                 committed; every status/component decision lives here
        │  build.py                      (make build)
        ▼
docs/data.json                          committed; what the page loads
```

`reference/` is local-only and not committed, so a fresh clone can build and
test without it; the importer skips itself when its inputs are missing. All
judgement happens in Python at build time; the page only filters and groups.

`data/grids.yaml` and `data/vertical.yaml` hold the horizontal cell counts and
other dimension sizes `build.py` prices a variable with (its dimensions come from
the source catalogue, through the importer). `data/aliases.yaml` holds reviewed
spreadsheet-name renames; `data/mom_fields.yaml` and `data/cice_fvars.yaml` are
frozen name lists the namelist export validates against. Requests at `fx`,
`subhr` and `dec` frequencies are listed with their CMIP7 label like any other.

## Limitations

- One experiment at a time; no ensemble or multi-experiment arithmetic.
- The log evidence is per component, not per line, and the MOM6 (ocn) log has no
  field list; ocean variables are mostly `●` from the MOM6 and MARBL source.
- Volume (GB per simulated year, raw uncompressed, top-right total and a column
  per line) is secondary and a **lower bound**: 4 bytes times the grid's cells
  times the dimensions the CESM3 source gives the field, so any variable the
  source did not resolve (all `◐ spreadsheet only`), any dimension without a size
  in `data/grids.yaml`, and any `fx`/`subhr` line is unpriced and left out. Land
  fields are priced as gridded output. The default is `ne30pg3_t233` (CAM-SE
  ~1°, tx2_3v3 ocean) with CAM7 middle-top (93 levels).

## Development

Everything runs in Docker.

```
make test          # pytest
make build         # regenerate docs/data.json from data/cmip7_request.yaml
make import-cmip7  # regenerate data/cmip7_request.yaml (needs reference/)
make dev           # http://localhost:8000, rebuilds and reloads on save
make shell
```

Commit `data/cmip7_request.yaml` and `docs/data.json` together; tests fail if
either is stale.

```
build.py             data/cmip7_request.yaml → docs/data.json
tools/               importer, log extractor, dev server, screenshot helper — see tools/README.md
tests/               pytest suite
docs/index.html      the page: one file, vanilla JS
cesm-field-scraper/  standalone scraper of CESM3 source for registerable fields
```

## License

See [LICENSE](LICENSE).
