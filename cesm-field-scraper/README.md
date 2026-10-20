# cesm-field-scraper

Reads the CESM `cesm3_0_alpha09e` (or `cesm3_0_alpha11d`: `make build run TAG=cesm3_0_alpha11d OUT=out-alpha11d`) source and writes YAML listing every
history field each component can register: name, dims, units, long name,
and the source line. The Dockerfile is the record of how the YAML was made.
The scraper depends on nothing else in this repository; the repository's importer
(`tools/import_cmip7.py`) reads its output, and `compare_logs.py` reads the run logs
under `../reference/` when they exist.

```
make build    # ~2 min: clone CESM at the pinned commit, git-fleximod the six components
make run      # ~10 s: writes out/<component>.yaml and out/submodules.txt
make test     # pytest on synthetic snippets, no checkout needed
```

Without make: `python -m cesm_fields <CESM checkout> <out dir>` (needs PyYAML).

It's deliberately bespoke to this one tag: the call signatures, CICE/MOM6
shape tables and CAM chemistry package were all checked against this tag's
source. Another tag means a new Dockerfile and
re-checking those against the output.

## Output

`out/<component>.yaml` for `atm` (CAM), `lnd` (CTSM), `ice` (CICE), `ocn`
(MOM6), `glc` (CISM) and `rof` (MOSART). `out/submodules.txt` lists every
repo in the checkout with its commit and tag.

There is one record per registration call site:

```yaml
- name: H2OSOI
  dims: [levsoi]          # non-horizontal dims, ncdump order, no time
  horizontal: column      # component-specific token, explained at the top of each file
  time: true
  units: mm3/mm3
  long_name: volumetric soil water (natural vegetated and crop landunits only)
  avgflag: A
  name_variants: water_tracers
  registrar: hist_addfld2d
  source: src/biogeophys/WaterStateType.F90:223
```

Horizontal dims are separate because for CAM and CTSM they depend on case
configuration. CAM's `physgrid` is `ncol` on spectral-element grids and
`lat, lon` on finite-volume. A CTSM field's subgrid level is its horizontal
dim only for vector output.

When a name is built at runtime, the record keeps the source expression as
`name_expr`:

- **With a `name`:** the expression was expanded. For example, CAM's
  `sflxnam(m)` gives `SFQ`, `SFso4_a1`, …, one record each.
- **With `name: null`:** it couldn't be resolved. `name_patterns` holds the
  part the source does fix (`ABSORB*`).
- **`dims: null` + `dims_expr`:** the shape argument didn't resolve.

## CAM constituents

CAM registers constituent fields (`Q`, `O3`, `SFso4_a1`, `so4_a1_SRF`, …) in
loops over `cnst_name(m)`. The scraper expands those loops with what the
baseline configuration's CAM build registers:

- `Q`
- PUMAS's `cnst_names`
- the species of each configuration's chemistry package (`chem` in `configurations.yaml`,
  e.g. `trop_strat_mam5_t4s2`, 154 constituents, or `ghg_mam4`); `CHEM` in `components/cam.py`
  without configurations. A name only some packages produce gets `requires: {chem: [...]}`.

The same package's `mo_sim_dat.F90` `rxt_tag_lst` names the per-reaction fields (`jno2`,
`usr_*`, and `r_*` from `rate_diags.F90`), and its `rxn_rate_sums` in `namelist_defaults_cam.xml`
names the rate sums (`O3_Loss`, `OddOx_Loss_Tot`, ...; build-namelist adds them only when the
mechanism has `O3S`).

Some loops are resolved from the package's tables rather than expanded over every constituent:

- The modal-aerosol column tendencies, from each file's `dotend` rules (`modal_names` in `components/cam.py`).
  The modes are the package's `*_aN` constituents (as build-namelist's `mode_defs`, mode types by mode
  count); a "pair" is a from-mode species and its to-mode namesake (same name less the mode digit).
  - `modal_aero_calcsize[_cam].F90`: every mode's number (`_sfcsiz1/2`); the aitken -> accum pair (`_sfcsiz3/4`).
  - `modal_aero_gasaerexch[_cam].F90`: `_sfgaex1` for H2SO4, NH3, MSA, SOAG*, each mode's so4/soa (nh4 with
    NH3) and the primary-carbon -> accum aging pair; `_sfgaex2` for both ends of every rename pair
    (cam7's `modal_accum_coarse_exch`: aitken->accum, accum<->coarse, or accum<->coarse_strat in MAM5).
  - `modal_aero_coag[_cam].F90`: `_sfcoag1` for aitken->accum, pcarbon->accum, aitken->pcarbon and aging.
  - `modal_aero_newnuc[_cam].F90`: `_sfnnuc1` for H2SO4 and aitken number/so4 (nh4 and NH3 if present).
  - Cloud-borne copies (`_cN`) for calcsize and `_sfgaex2`.
- `tracer_cnst.F90` (prescribed oxidants, `[lev]`): the species build-namelist puts in
  `tracer_cnst_specifier` (`O3`, `OH`, `NO3`, `HO2`, `HALONS`) that are the package's invariants
  (`inv_lst`, which also names `mo_setinv`'s `<inv>_dens`/`_vmr`). So `ghg_mam4` gets all five,
  `trop_strat_mam5_t4s2` (solves them) none. A `user_nl_cam` specifier can add others.

- `modal_aero/aero_model.F90` (`<species>DDF/TBF/GVF/DTQ/DDV`): `drydep_list` is the `aer_drydep_list`
  namelist, which build-namelist makes from the package's species found in
  `bld/namelist_files/mozart_master_aer_drydep_list.xml` (the declaration's blank default is not a name).
- `physics/cam/aoa_tracers.F90` (`AOA1`, `HORZ`, `VERT` and their `*SRC`): the module's own `c_names`,
  under the `aoa_tracers` axis (bld/configure's `age_of_air_trcs`, on for `trop_strat_*`/`waccm_*`
  chemistry, so on for BHISTE_MTt4s and off for BHISTC_MTso).

The modal files reuse one `fieldname` for every call, so each call takes the `fieldname` assignment just before it.

It also expands the per-constituent name arrays built in `constituents.F90`
(`sflxnam`, `ptendnam`, …). An index that names one constituent
(`call cnst_get_ind('CLDICE', ixcldice)`, then `ptendnam(ixcldice)`) resolves to that one name.
A loop over a subset of constituents still expands to all of them, so expanded
records can over-claim; their `alternatives` count says by how much.

## Checked against a real alpha09e run

The run log under `../reference/` is an MTso (`ghg_mam4`) run; there is no MTt4s log. The table below
scored it against `BHISTE_MTt4s` before that was known. Against `BHISTC_MTso` on alpha11d output
every modal-aerosol tendency (`*_sfcsiz*`, `*_sfgaex1/2`, `*_sfcoag1`,
`*_sfnnuc1`), aerosol dry-deposition (`*DDF/TBF/GVF/DTQ/DDV`), `<inv>_dens/_vmr` and prescribed-oxidant
name matches the log exactly (none missing, none extra); CAM recall is 59% exact.

| | names in the log | exact | pattern only | not found |
|---|---|---|---|---|
| CAM | 3245 | 50% | 38% | 12% |
| CTSM | 1922 | 77% | 19% | 4% |
| MOSART | 27 | 19% | 81% | 0% |
| CICE (active subset) | 121 | 100% | – | 0% |

CTSM's "not found" names are mostly carbon-isotope variants (`C13_…`, `C14_…`, 44 of 78) and decomposition-cascade
pools built in nested loops, 18 of them names the log truncates at 32 characters. Nearly all of CAM's (380 of 389) are
numbered names built with `write(fldname,'(a,i2.2)')` (`AODDUST01`, `TAUXSp12`, …), which the scraper does not expand. Every CAM name found in the log has a
vertical dim that agrees with the log's level count.

The source also registers fields this run doesn't use. The report splits CAM's exact names by how certain the
source is: about three quarters of names registered by a literal call are in the log, against about a sixth of
those expanded from large loops, because loops over constituents are decided by data files at run time. This
tool lists what the source *can* register, not what one case *does*.

## Configurations

The source registers more than any case writes, so each record may carry `requires`: axis -> allowed
values, taken from where it was found (`cesm_fields/config.py`: dycore, chemistry package, physics
options, SCAM, debug, FATES, MARBL, CISM). `configurations.yaml` gives the value of every axis for a
named case, e.g. `BHISTE_MTt4s`, and `cesm_fields.config.active(record, config)` evaluates it.
Conditions inside a file (an `if (use_cn)` around a call) are not read.

An expanded record also has `alternatives`: how many names its call site expands to. A large number
means a loop whose members the run decides (which constituents exist), so treat it as "possible", not "registered".

`python compare_logs.py out ../reference/log_files/extracted_fields.yaml configurations.yaml BHISTE_MTt4s`
scores a configuration against a real run's log (recall, pattern-only, other-config, missing).

**Namelist-driven pruning (atm).** `cesm_fields/flow.py` reads each configuration's `cam_config`
(the attributes `bld/configure` would set), resolves `namelist_defaults_cam.xml` to the namelist values, then
walks the Fortran: `if`/`select case` guards, the call graph from routines nothing calls, derived logicals
(`is_clubb_scheme = eddy_scheme == 'CLUBB_SGS'`), and the CCPP suite (`suite_<ccpp_suite>.xml` decides which
scheme files run). A registration the namelist rules out gets `inactive_in: [<configuration>]`.
It is permissive: a guard on a value it does not know counts as possibly true, so it only removes, never adds.

Besides call-site scraping, two more sources feed `ocn` and `lnd`: MARBL's
`diagnostics_latest.yaml` (templates expanded per autotroph/zooplankton) together with the output of
CESM's own `MOM_MARBL_diagnostics.py`, and FATES's `set_history_var` calls.

## Layout

```
cesm_fields/fortran.py      statements, call arguments, literals, name expansion
cesm_fields/common.py       file walking, record format
cesm_fields/components/     one module per component
cesm_fields/config.py       which configuration registers a record (`requires`, `active`)
cesm_fields/flow.py         namelist-driven pruning of CAM registrations
cesm_fields/__main__.py     CLI, YAML writer
configurations.yaml         named configurations (BHISTE_MTt4s)
compare_logs.py             score a configuration against run logs
docker/cesm3_0_alpha09e.Dockerfile
```
