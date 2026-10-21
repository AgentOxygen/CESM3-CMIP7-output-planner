# Notes: MTt4s / additional (non-CMIP7) variables

Status: **atmosphere wired**. "Simone's additions" (list 1 below, 154 names) apply in both
configurations: all are registered in the MTso log. Only the chemistry-only additions (120) need
MTt4s. Land and ocean are labelled "(not implemented)".

Source reviewed: a generated CAM namelist (`gen_cam_cmip7_only.py`, CMIP7 request table
v1.2.2.5.26Oct14, field check against the beta09 MTso master field list; stands in for alpha11b).
It uses `empty_htapes = .true.` and tapes `h0`..`h9`.

## It holds three different sets of names

1. **Simone's additions (not CMIP7)**: about 190 names on `h0`, 8 on `h2`, and all 23 on `h9`.
   Written against the **MTso** master list, so these are standard-configuration extras,
   not interactive-chemistry fields.
2. **"Simone's fields NOT in the MTso master list"** (about 150 names): chemistry species and rates
   (`CO`, `NO`, `O3_Loss`, `OddOx_*`, `HCL`, `TMCLY`, ...). The closest thing to an MTt4s-only set.
3. **"CMIP7 CAM fields NOT in the MTso master list"** (about 130 names): CMIP7-requested fields MTso
   cannot write. These are CMIP7 variables, so they are not "additional (not CMIP7)"; they would be a
   status change on existing rows, or their own category.

Lists 2 and 3 overlap (`AOA1`, `CFC113`, `CFC114`, `CH2O`, `CH3COCH3`, ...).

**Open question:** which of lists 2 and 3 "interactive chemistry" turns on, and whether both.

## What wiring it in needs

- **Frequency:** `h9` is a 5-day instantaneous tape (`nhtfrq = -120`, 73 samples/yr). Not a CMIP7
  label, so `per_year` and the frequency filter need a new entry.
- **Time method:** additions on `h0`/`h2` carry no `:A`/`:I` flag, CMIP7 lines do. Lines are keyed
  `name|method|freq`, so each addition needs a method (probably the default mean).
- **No audit data:** no compound name, UID, spreadsheet line or priority. The detail pane needs its
  own content (e.g. "Simone's request, tape h0"). Rows need the ✚ icon (blue, legend entry exists).
- **Pricing:** needs a source-catalogue record; chemistry species the MTso-based source does not
  register will be unpriced. This is why the catalogue is being rebuilt from `cesm3_0_alpha11d`.
- **CLM fields:** the file's footer lists CLM names written for atmos/aerosol rows
  (`QSNOFRZ`, `SNOCAN`, ...). Relevant to the land option.
- **Not checked:** whether the file's tape layout (`nhtfrq`, `mfilt`, `ndens`) matches what
  `namelist.js` emits.
