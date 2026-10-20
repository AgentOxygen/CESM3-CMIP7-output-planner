"""atm: CAM. `addfld` (legacy physics) and `history_add_field` (CCPP schemes).

    call addfld('T', (/ 'lev' /), 'A', 'K', 'Temperature', gridname='physgrid')
    call history_add_field('HR', 'Heating rate ...', 'lev', 'avg', 'K s-1')

The dims argument names only non-horizontal dims; `horizontal` is the
`gridname` (default `physgrid`, per addfld_nd in src/control/cam_history.F90).

Constituent fields (`Q`, `O3`, `SFso4_a1`, `so4_a1_SRF`, ...) are registered
in loops over `cnst_name(m)`. Those loops are expanded with the constituents
a CAM7 build registers: `Q` (physics/cam/physpkg.F90), the PUMAS
`cnst_names` array, and the species of each configuration's chemistry package
(`chem` in configurations.yaml; `CHEM` without one). A loop over a subset of
constituents still expands to all of them, so an expanded record can
over-claim; its `name_expr` says it was expanded.
"""

import re

from .. import config, fortran
from ..common import calls, read, records

COMPONENT, MODEL, REPO_PATH = "atm", "CAM", "components/cam"

HORIZONTAL = ("CAM grid name. physgrid is [ncol] on spectral-element grids and "
              "[lat, lon] on finite-volume; other names (GLL, fv_centers_zonal, ...) "
              "are CAM's other registered grids.")

CHEM = "trop_strat_mam5_t4s2"      # default without configurations (BHISTE_MTt4s: -chem for %CT4S2)


def constituent_arrays(chem):
    return [("src/physics/cam7/micro_pumas_cam.F90", "cnst_names"),
            (f"src/chemistry/pp_{chem}/mo_sim_dat.F90", "solsym")]


CONSTITUENT_ARRAYS = constituent_arrays(CHEM)


def known_names(root, chem=CHEM):
    """Variable -> the names it can hold, for expanding constituent loops."""
    cnst = ["Q"]
    for rel, var in constituent_arrays(chem):
        cnst += _array(root / rel, var)
    tags = _array(root / f"src/chemistry/pp_{chem}/mo_sim_dat.F90", "rxt_tag_lst")
    known = {"cnst_name": cnst, "solsym": cnst,
             # cloud-borne copies of the aerosol species (modal_aero_data: `_a<mode>` -> `_c<mode>`)
             "cnst_name_cw": [re.sub(r"_a(\d+)$", r"_c\1", c) for c in cnst if re.search(r"_a\d+$", c)],
             # mo_gas_phase_chemdr: one field per reaction tag (photolysis `jno2`, rate constants `usr_*`)
             "tag_names": tags,
             # rate_diags: 'r_'//tag, dropping the first 4 characters when the tag has a tag_/usr_/cph_/ion_ prefix
             "rate_names": ["r_" + (t[4:] if any(p in t for p in ("tag_", "usr_", "cph_", "ion_")) else t) for t in tags],
             "rxn_rate_sums": rxn_rate_sums(root, chem) if "O3S" in cnst else []}
    # mo_setinv: `<inv>_dens`, `<inv>_vmr`; tracer_cnst: the prescribed invariants
    invariants = _array(root / f"src/chemistry/pp_{chem}/mo_sim_dat.F90", "inv_lst")
    known["inv_lst"] = invariants
    known["__tracer_cnst__"] = [n for n in tracer_cnst_names(root) if n in invariants]
    known["__modal__"] = modal_names(cnst)
    known["__aer_drydep__"] = aer_drydep_list(root, cnst)
    known["__nmodes__"] = sum(bool(re.fullmatch(r"num_a\d+", c)) for c in cnst)
    # build-namelist: cam6/cam7 `_mam` chemistry sets modal_strat_sulfate when the mechanism has OCS
    known["__strat_sulfate__"] = "OCS" in cnst
    # constituents.F90 builds public per-constituent name arrays used all over
    # CAM (`sflxnam(m) = 'SF'//cnst_name(m)`, ptendnam, tottnam, ...).
    env = fortran.assignments(fortran.statements(read(root / "src/physics/cam/constituents.F90")))
    templates = {}
    for var, rhs in env.items():
        if any("cnst_name" in r for r in rhs):
            known[var] = sorted({n for r in rhs for n in fortran.expand(r, {}, known)})
            templates[var] = rhs
    known["__templates__"] = templates
    return known


def _array(path, var):
    """Every string in `var(...) = (/ ... /)` assignments in one file (mo_sim_dat's solsym, rxt_tag_lst)."""
    out = []
    for _, text in fortran.statements(read(path)):
        if m := re.search(rf"\b{var}\s*(\([^=]*\))?\s*=\s*(\(/.*/\))$", text, re.I | re.S):
            out += fortran.literal_list(m.group(2))
    return out


def rxn_rate_sums(root, chem):
    """Names of the reaction-rate sums (`O3_Loss`, `OddOx_Loss_Tot`, ...) namelist_defaults_cam.xml gives
    `chem`; build-namelist adds `rxn_rate_sums` only when the mechanism has O3S (or for WACCM-X)."""
    xml = read(root / "bld/namelist_files/namelist_defaults_cam.xml")
    m = (re.search(rf'<rxn_rate_sums\s+chem="{chem}"\s*>(.*?)</rxn_rate_sums>', xml, re.S)
         or re.search(r"<rxn_rate_sums>(.*?)</rxn_rate_sums>", xml, re.S))
    return re.findall(r"'\s*(\w+)\s*=", m.group(1)) if m else []


def tracer_cnst_names(root):
    """Every species build-namelist ever puts in `tracer_cnst_specifier` (prescribed oxidants:
    'O3','OH','NO3','HO2','HALONS'). tracer_cnst_init stops the run unless each is one of the package's
    invariants, so the caller intersects this with `inv_lst`. A user_nl specifier can add others."""
    if not (root / "bld/build-namelist").exists():          # synthetic test trees
        return []
    text = read(root / "bld/build-namelist")
    vals = re.findall(r"'tracer_cnst_specifier',\s*'val'\s*=>\s*\"([^\"]*)\"", text)
    vals += re.findall(r"my \$val\s*=\s*\"([^\"]*)\";\s*add_default\(\$nl,\s*'tracer_cnst_specifier'", text)
    return sorted({n.split(":")[0].split("=")[0].strip() for v in vals for n in re.findall(r"'([^']+)'", v)})


# MAM mode types in mode order, by number of modes (build-namelist: @mode_types for 3/4/5/7 modes)
MODE_TYPES = {3: ["accum", "aitken", "coarse"],
              4: ["accum", "aitken", "coarse", "primary_carbon"],
              5: ["accum", "aitken", "coarse", "primary_carbon", "coarse_strat"],
              7: ["accum", "aitken", "primary_carbon", "fine_seasalt", "fine_dust", "coarse_seasalt", "coarse_dust"]}


def modal_names(cnst):
    """Species each modal-aerosol column-tendency diagnostic registers, keyed by suffix, as
    {suffix: {"a": names, "b": names}} ("b": the `tmpnameb` side of a pair). The package's modes are its
    `*_aN` constituents (build-namelist builds `mode_defs` from them); the rules are each file's `dotend`:

    - `_sfcsiz1/2` (calcsize): every mode's number. `_sfcsiz3/4`: the aitken -> accum pair (number and each
      aitken species with an accum namesake: names equal less the mode digit, as modal_aero_rename_cam).
    - `_sfgaex1` (gasaerexch): H2SO4, NH3, MSA, SOAG*, each mode's so4/nh4 (with NH3)/soa*, and the
      primary-carbon -> accum aging pair (number, every pcarbon species, their accum namesakes).
    - `_sfgaex2`: both ends of every rename pair. cam7 sets modal_accum_coarse_exch, so the pairs are
      aitken->accum, accum->coarse, coarse->accum (coarse_strat in place of coarse when the package has it).
    - `_sfcoag1` (coag): aitken->accum, pcarbon->accum, aitken->pcarbon (effective accum): every species of
      the from-mode, its namesake in the effective to-mode, both modes' number; plus the aging pair.
      Without a pcarbon mode only aitken->accum (pair_option_acoag 1).
    - `_sfnnuc1` (newnuc): H2SO4, aitken number and so4, and aitken nh4 with NH3 when both exist.
    Cloud-borne copies (`_c`, cnst_name_cw) exist for calcsize and `_sfgaex2`."""
    nmodes = sum(bool(re.fullmatch(r"num_a\d+", c)) for c in cnst)
    types = MODE_TYPES.get(nmodes, [])
    mode = {t: i + 1 for i, t in enumerate(types)}
    spec = {m: [c for c in cnst if re.fullmatch(rf"(?!num_)\w+_a{m}", c)] for m in range(1, nmodes + 1)}
    num = lambda m: [f"num_a{m}"] if m else []
    twin = lambda c, m: next((t for t in spec.get(m, []) if t[:-len(str(m))] == c[:c.rindex("_a") + 2]), None)
    cw = lambda names: names + [re.sub(r"_a(\d+)$", r"_c\1", n) for n in names]
    uniq = lambda names: list(dict.fromkeys(n for n in names if n))

    def pair(frm, too, keep_all=False):          # (from side, to side): numbers, then species
        if not (frm and too):
            return [], []
        f = [c for c in spec[frm] if keep_all or twin(c, too)]
        return num(frm) + f, num(too) + [twin(c, too) for c in f]

    ait, acc, pca = mode.get("aitken"), mode.get("accum"), mode.get("primary_carbon")
    crs = mode.get("coarse_strat") or mode.get("coarse")
    has = lambda c: c in cnst
    aging = pair(pca, acc, keep_all=True) if acc and f"so4_a{acc}" in cnst else ([], [])
    gaex1 = [c for c in ("H2SO4", "NH3", "MSA") if has(c)] + [c for c in cnst if re.fullmatch(r"SOAG\d*", c)]
    for m in range(1, nmodes + 1):
        gaex1 += [c for c in spec[m] if re.fullmatch(rf"(so4|soa\d*)_a{m}", c) or (has("NH3") and c == f"nh4_a{m}")]
    gaex1 += aging[0] + aging[1]
    rename = [pair(ait, acc), pair(acc, crs), pair(crs, acc)]
    coag = [pair(ait, acc, True), pair(pca, acc, True), pair(ait, acc, True)] if pca else [pair(ait, acc, True)]
    coag_names = [n for f, t in coag for n in f + t] + num(pca) + aging[0] + aging[1]
    nnuc = ["H2SO4"] + num(ait) + [f"so4_a{ait}"] + ([f"nh4_a{ait}", "NH3"] if has("NH3") and has(f"nh4_a{ait}") else [])
    size_frm, size_too = pair(ait, acc)
    both = lambda names: {"a": uniq(names), "b": uniq(names)}
    numbers = both(cw([c for c in cnst if re.fullmatch(r"num_a\d+", c)]))
    return {"_sfcsiz1": numbers, "_sfcsiz2": numbers,
            "_sfcsiz3": {"a": uniq(cw(size_frm)), "b": uniq(cw(size_too))},
            "_sfcsiz4": {"a": uniq(cw(size_frm)), "b": uniq(cw(size_too))},
            "_sfgaex1": both(gaex1),
            "_sfgaex2": both(cw([n for f, t in rename for n in f + t])),
            "_sfcoag1": both(coag_names),
            "_sfnnuc1": both([n for n in nnuc if has(n)])}


# Modal-aerosol files whose `dotend` loops `modal_names` resolves (alpha11d `*_cam.F90`, alpha09e originals).
# They reuse one `fieldname` for every call, so each call takes the assignment just before it.
MODAL = {f"src/chemistry/{d}/modal_aero_{f}{v}.F90" for d, f in
         [("utils", "calcsize"), ("modal_aero", "gasaerexch"), ("modal_aero", "coag"), ("modal_aero", "newnuc")]
         for v in ("", "_cam")}


def aer_drydep_list(root, cnst):
    """modal aero_model's `drydep_list` (the `aer_drydep_list` namelist): build-namelist's
    get_dep_list keeps the package's species that are in mozart_master_aer_drydep_list.xml
    (all aerosol species here; the not-transported exception is gas-only)."""
    path = root / "bld/namelist_files/mozart_master_aer_drydep_list.xml"
    if not path.exists():                                    # synthetic test trees
        return []
    master = {n for body in re.findall(r"<list[^>]*>(.*?)</list>", read(path), re.S)
              for n in re.split(r"[\s,]+", body) if n}
    return sorted(c for c in cnst if c in master)


AERO_MODEL = "src/chemistry/modal_aero/aero_model.F90"
AOA_TRACERS = "src/physics/cam/aoa_tracers.F90"


# `write(dgnum_name(n),fmt='(a,i1)') 'dgnum',n` before `call addfld(dgnum_name(n), ...)`
_NUMBERED = re.compile(r"""^write\s*\(\s*(\w+)\s*(?:\([^)]*\))?\s*,\s*(?:fmt\s*=\s*)?'\(a\d*,i(\d)(?:\.(\d))?\)'\s*\)\s*'(\w+)'\s*,\s*\w+\s*$""", re.I)
STRAT_SULFATE = {"wtpct_a", "sulfeq_a", "sulden_a"}       # inside `if (modal_strat_sulfate)`


def _mode_numbered(call, stmts, k):
    """Names for an aero_model.F90 addfld whose name was written by a per-mode `write` (loop n = 1,
    ntot_amode): prefix + mode number, one per mode of the package. None if the call isn't one."""
    if not (m := re.match(r"^\s*(\w+)", call.args[0])):           # a literal name
        return None
    var = m.group(1).lower()
    writes = [m for line, t in stmts if line < call.line and (m := _NUMBERED.match(t)) and m.group(1).lower() == var]
    if not writes:
        return None
    _, width, pad, prefix = writes[-1].groups()
    if prefix in STRAT_SULFATE and not k["__strat_sulfate__"]:
        return []
    return [prefix + str(n).zfill(int(pad or 0)).rjust(int(width)) for n in range(1, k["__nmodes__"] + 1)]


def _call_known(rel, call, stmts, k, env=None):
    """(env override, known override, patterns) for one call site in a file that needs one."""
    if rel == "src/chemistry/mozart/rate_diags.F90":
        return {}, {"grp%name": k["rxn_rate_sums"]}, None
    if rel == "src/chemistry/mozart/tracer_cnst.F90":
        return {}, {"fields%fldnam": k["__tracer_cnst__"]}, None
    if rel == AERO_MODEL and (numbered := _mode_numbered(call, stmts, k)) is not None:
        return {}, {}, numbered
    if rel == AERO_MODEL:                    # `drydep_list = ' '` is only the declaration's blank default
        return {}, {"drydep_list": k["__aer_drydep__"]}, None
    if rel == AOA_TRACERS and "c_names" in (env or {}):     # cnst_name(ifirst+m-1): this module's own tracers
        names = fortran.literal_list(env["c_names"][0])
        return {}, {"cnst_name": names if isinstance(names, list) else []}, None
    if rel not in MODAL or not (var := re.match(r"^\s*(?:trim\s*\()?\s*(\w+)", call.args[0])):
        return {}, {}, None
    var = var.group(1).lower()
    before = [t for line, t in stmts if line < call.line and re.match(rf"^{var}\s*=(?!=)", t, re.I)]
    rhs = before[-1].split("=", 1)[1] if before else call.args[0]
    env = {var: [rhs]} if before else {}
    if not (m := re.search(r"'(_sf\w+)'", rhs)) or m.group(1) not in k["__modal__"]:
        return env, {}, None
    names = k["__modal__"][m.group(1)]["b" if "tmpnameb" in rhs.lower() else "a"]
    if "_cw" in rhs.lower():
        names = [n for n in names if re.search(r"_c\d+$", n)]
    elif re.search(r"cnst_name\s*\(", rhs, re.I):
        names = [n for n in names if not re.search(r"_c\d+$", n)]
    return env, {}, [n + m.group(1) for n in names]


def constituent_indexes(text):
    """`call cnst_get_ind('CLDICE', ixcldice)` -> {'ixcldice': 'CLDICE'}: index variables that name one constituent."""
    return {m.group(2).lower(): m.group(1) for m in
            re.finditer(r"cnst_get_ind\s*\(\s*'([^']+)'\s*,\s*(\w+)", text, re.I)}


def _dims(text):
    if text.strip().lower() == "horiz_only":
        return []
    one = fortran.literal(text)
    return [one.strip()] if isinstance(one, str) else fortran.literal_list(text)


def scrape(root, chems=(CHEM,)):
    """Constituent loops are expanded once per chemistry package in `chems`; a name only some
    packages produce gets `requires: {chem: [those]}`."""
    knowns, indexes, stmts = {c: known_names(root, c) for c in chems}, {}, {}
    for rel, routine, call, env in calls(root, "src", ["addfld", "history_add_field"]):
        if rel not in indexes:
            text = read(root / rel)
            indexes[rel] = constituent_indexes(text)
            stmts[rel] = list(fortran.statements(text)) if rel in MODAL | {AERO_MODEL} else []
        own = config.requires(rel + ":0").get("chem", [None])[0]          # a pp_<chem>/ file: only its own package
        per_chem = {}
        for c, k in knowns.items():
            if own in knowns and c != own:
                continue
            env_over, known_over, patterns = _call_known(rel, call, stmts[rel], k, env)
            per_chem[c] = _records(routine, call, env={**env, **env_over},
                                   known={**k, **known_over, "__index__": indexes[rel]},
                                   registrar=routine, source=f"{rel}:{call.line}", patterns=patterns)
        merged = {}
        for c, recs in per_chem.items():
            for r in recs:
                merged.setdefault(r["name"] or tuple(r.get("name_patterns", ())), (r, []))[1].append(c)
        # a package that left part of the name unresolved (too many alternatives) can't rule out the others' names
        gave_up = [c for c, recs in per_chem.items() if any(r["name"] is None for r in recs)]
        for r, cs in merged.values():
            cs = [c for c in per_chem if c in cs or (r["name"] and c in gave_up)]
            if len(cs) < len(per_chem) and "chem" not in r.get("requires", {}):
                r["requires"] = {**r.get("requires", {}), "chem": cs}
            yield r


def _records(routine, call, **common):
    if routine == "addfld":
        grid = call.kw.get("gridname")
        return records(
            name=fortran.name(call.args[0]), dims=_dims(call.args[1]),
            horizontal="physgrid" if grid is None else fortran.literal(grid),
            units=fortran.literal(call.args[3]), long_name=fortran.literal(fortran.arg(call, 4, "long_name")),
            avgflag=fortran.literal(call.args[2]), **common)
    return records(
        name=fortran.name(call.args[0]), dims=_dims(call.args[2]), horizontal="physgrid",
        units=fortran.literal(call.args[4]), long_name=fortran.literal(call.args[1]),
        avgflag=fortran.literal(call.args[3]), **common)
