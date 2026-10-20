// Builds a CESM user_nl_* history block from the page's selected rows.
// Pure functions, no DOM: the page calls Namelist.build(), tests/test_namelist.py
// drives the same file under node. Every rule below was read from the CESM3 source (tag
// alpha09e): CAM cam_history.F90, CTSM histFileMod.F90, MOSART mosart_histfile.F90, CICE
// ice_history*.F90, CISM namelist_definition_cism.xml, MOM6 cime_config/buildnml and param_templates.
(function (root) {
  // CMIP7 frequency -> [nhtfrq, mfilt]. Negative nhtfrq = hours; 0 = monthly.
  // -8760 / -87600 assume the 365-day calendar. mfilt is file packaging only.
  // fx and subhr have no entry, so they are dropped and listed.
  const FREQ = { mon: [0, 1], dec: [-87600, 1], yr: [-8760, 1], day: [-24, 30],
                 "6hr": [-6, 120], "3hr": [-3, 240], "1hr": [-1, 720] };
  const ORDER = ["mon", "dec", "yr", "day", "6hr", "3hr", "1hr"];   // tape order: monthly first, then coarse -> fine

  const COMPONENTS = {
    atm: { file: "user_nl_cam", pre: "", flags: "ABILMNSX", maxName: 32, maxTapes: 10,
           empty: "empty_htapes" },
    lnd: { file: "user_nl_clm", pre: "hist_", flags: ["A", "I", "X", "M", "SUM"], maxName: 64, maxTapes: 10,
           empty: "hist_empty_htapes", dov2xy: true },
    // MOSART has no empty_htapes: its default fields stay on, so this file only adds to them.
    rof: { file: "user_nl_mosart", pre: "", flags: "AIXM", maxName: 80, maxTapes: 3, empty: null },
    // CISM: one stream of whole years, a single space-delimited variable string. See buildGlc.
    glc: { file: "user_nl_cism", glc: true },
    // CICE: stream letters in histfreq/histfreq_n, and a per-field f_<name> mask of those letters. See buildIce.
    ice: { file: "user_nl_cice", ice: true },
    // MOM6: not a namelist but an FMS diag_table; this is the unresolved form CESM copies from SourceMods.
    ocn: { file: "diag_table.unresolved", ocn: true },
  };
  const q = (s) => `'${s}'`;

  const WIDTH = 100;          // wrap lists here; Fortran namelist lines must stay under 132
  // Pack pre-formatted items onto lines at most WIDTH wide: `first` starts the first line, `indent` the rest.
  function pack(first, items, indent, sep) {
    const lines = []; let cur = first, n = 0;
    items.forEach((it, i) => {
      const tok = it + (i < items.length - 1 ? sep : "");
      if (n && cur.length + tok.length > WIDTH) { lines.push(cur.trimEnd()); cur = indent; n = 0; }
      cur += tok; n++;
    });
    lines.push(cur.trimEnd());
    return lines;
  }

  // Wrap comment lines (! or #) longer than WIDTH at word boundaries; the continuation keeps the comment character.
  // Settings lines and the diag_table's field lines are never touched.
  function wrapComments(text) {
    return text.split("\n").flatMap(l => {
      const m = l.match(/^([!#]+) (\S.*)$/);
      if (!m || l.length <= WIDTH) return [l];
      const cont = m[1] + "   ", out = [];
      let cur = m[1] + " ", fresh = true;
      for (const w of m[2].split(" ")) {
        if (!fresh && cur.length + 1 + w.length > WIDTH) { out.push(cur); cur = cont + w; }
        else { cur += (fresh ? "" : " ") + w; }
        fresh = false;
      }
      return out.concat(cur);
    }).join("\n");
  }

  // Closing blocks, so the settings come first: notes, what was left out (grouped by reason), and the names
  // with no CESM3 source or run-log evidence at all (those can abort a run). `c` is the comment character.
  function tail(rows, dropped, c, notes = []) {
    const L = [];
    if (notes.length) L.push("", `${c} --- notes ---`, ...notes);
    if (dropped.length) {
      const by = {};
      for (const d of dropped) (by[d.why] ||= []).push(`${d.name} (${d.freq})`);
      L.push("", `${c} --- not exported: ${dropped.length} line(s) ---`);
      for (const [why, ns] of Object.entries(by)) L.push(`${c} ${why}: ${ns.length}`, ...pack(`${c}   `, ns, `${c}   `, ", "));
    }
    const bad = [...new Set(rows.filter(r => (r.items || []).some(x => x.t && !["verified", "source"].includes(x.t.st))).map(r => r.name))].sort();
    if (bad.length) L.push("", `${c} --- no CESM3 source or run-log evidence (${bad.length}): an unknown name can abort the run ---`,
                           ...pack(`${c}   `, bad, `${c}   `, ", "));
    return L;
  }

  // Evidence lines every generator adds: lines with no CESM3 evidence at all, and lines only the source (not a run) vouches for.
  const evidence = (meta, comment) => [
    ...(meta.unverified ? [`${comment} ${meta.unverified} line(s) have no CESM3 source or run-log evidence: an unknown name can abort the run.`] : []),
    ...(meta.sourceOnly ? [`${comment} ${meta.sourceOnly} line(s) are registered by the CESM3 source${meta.sourceConfiguration ? ` for ${meta.sourceConfiguration}` : ""} but were not seen in a run log (names expanded from loops may not exist in every case).`] : [])];

  const header = (c, meta) => [
    `! Generated ${meta.date || new Date().toISOString().slice(0, 10)} by the CESM3-CMIP7-output-planner (CMIP7 -> CESM3 variable lists).`,
    `! ${c.file}: history output for the selection on the page.`,
    ...(meta.title ? [`! ${meta.title}`] : [])];

  // CISM writes one history stream every N whole years. The default file takes the coarsest
  // requested frequency; each other expressible frequency gets a variant file to swap in.
  const GLC_YEARS = { yr: 1, dec: 10 };
  function buildGlc(c, rows, meta) {
    const dropped = [], byFreq = {};
    for (const r of rows) {
      if (!GLC_YEARS[r.freq]) { dropped.push({ name: r.name, freq: r.freq, why: "CISM history is whole years: only yr and dec can be written" }); continue; }
      (byFreq[r.freq] ||= new Set()).add(r.name);
    }
    const freqs = Object.keys(byFreq).sort((a, b) => GLC_YEARS[b] - GLC_YEARS[a]);   // coarsest first
    const one = (f, variant) => {
      const L = [...header(c, meta),
        ...(variant ? [`! Writes the ${f} variables only (every ${GLC_YEARS[f]} year(s)). CISM has one history stream per run.`,
                 `! Swap this in for ${c.file} to get ${f} output instead of the default file.`] : []),
        ...evidence(meta, "!"),
        `! esm_history_vars REPLACES CISM's default variable list.`];
      if (!f) return L.concat("! (nothing to export)", tail(rows, dropped, "!")).join("\n") + "\n";
      return L.concat("", ` esm_history_vars = '${[...byFreq[f]].sort().join(" ")}'`,
                      ` history_option = 'nyears'`, ` history_frequency = ${GLC_YEARS[f]}`, tail(rows, dropped, "!")).join("\n") + "\n";
    };
    return { text: one(freqs[0]), variants: freqs.slice(1).map(f => ({ freq: f, text: one(f, true) })), dropped };
  }

  // CICE has no field lists. histfreq/histfreq_n define up to 5 streams (letter + interval); each field's
  // f_<name> string lists the letters of the streams it appears on. A stream is found by its LETTER, so two
  // streams that share one (6hr and 3hr are both 'h'; yr and dec both 'y') cannot be told apart: the coarser wins.
  // CICE averages everything: a requested I/M/X is exported but noted. meta.iceFields = the valid f_ names.
  const ICE_STREAM = { mon: ["m", 1], day: ["d", 1], "6hr": ["h", 6], "3hr": ["h", 3], "1hr": ["h", 1], yr: ["y", 1], dec: ["y", 10] };
  function buildIce(c, rows, meta) {
    const valid = new Set(meta.iceFields || []), dropped = [], notes = [], masks = {}, used = {};
    const wanted = new Set(rows.map(r => r.freq));
    const streams = ORDER.filter(f => wanted.has(f) && ICE_STREAM[f]);
    for (const f of streams) {
      const [letter] = ICE_STREAM[f], clash = Object.keys(used).find(g => used[g] === letter);
      if (clash) dropped.push(...rows.filter(r => r.freq === f).map(r => ({ name: r.name, freq: f,
        why: `stream letter '${letter}' is already used by ${clash}; CICE cannot tell them apart` })));
      else used[f] = letter;
    }
    for (const r of rows) {
      if (!ICE_STREAM[r.freq]) { dropped.push({ name: r.name, freq: r.freq, why: `frequency ${r.freq} has no history setting` }); continue; }
      if (!used[r.freq]) continue;                                       // already reported as a clash
      // The spreadsheet's daily names carry a _d suffix on the same f_ variable.
      const v = valid.has(r.name) ? r.name : /_d$/.test(r.name) && valid.has(r.name.slice(0, -2)) ? r.name.slice(0, -2) : "";
      if (!v) { dropped.push({ name: r.name, freq: r.freq, why: "no f_ switch of that name in CICE" }); continue; }
      (masks[v] ||= new Set()).add(used[r.freq]);
      if (r.method && r.method !== "A") notes.push(`! ${v} (${r.freq}): ${r.method} requested but CICE averages every field`);
    }
    const act = streams.filter(f => used[f]);
    const L = [...header(c, meta),
      `! CICE cannot switch its defaults off: fields below are ADDED to the model's default output, and these`,
      `! histfreq/histfreq_n REPLACE its stream layout (a default mask such as 'mdhxx' follows the new letters).`,
      ...evidence(meta, "!")];
    if (!act.length) return { text: L.concat("! (nothing to export)", tail(rows, dropped, "!", notes)).join("\n") + "\n", dropped };
    const pad = (a, x) => a.concat(Array(5 - a.length).fill(x)).join(", ");
    L.push("", ` histfreq = ${pad(act.map(f => q(used[f])), q("x"))}`,
           ` histfreq_n = ${pad(act.map(f => ICE_STREAM[f][1]), 0)}`);
    for (const v of Object.keys(masks).sort())
      L.push(` f_${v} = ${q(act.map(f => used[f]).filter(l => masks[v].has(l)).join(""))}`);
    return { text: L.concat(tail(rows, dropped, "!", notes)).join("\n") + "\n", dropped };
  }

  // MOM6 diag_table. One file per (frequency, module); one line per field. [output, new-file, date format] per frequency.
  const MOM_FREQ = { mon: [[1, "months"], [1, "months"], "%4yr-%2mo"], day: [[1, "days"], [1, "months"], "%4yr-%2mo"],
    "6hr": [[6, "hours"], [1, "months"], "%4yr-%2mo"], "3hr": [[3, "hours"], [1, "months"], "%4yr-%2mo"],
    "1hr": [[1, "hours"], [1, "days"], "%4yr-%2mo-%2dy"], yr: [[1, "years"], [1, "years"], "%4yr"],
    dec: [[10, "years"], [10, "years"], "%4yr"] };
  const MOM_TAG = { ocean_model: "native", ocean_model_z: "z", ocean_model_rho2: "rho2" };
  // Time method -> diag_table reduction. A mean and I (".false.") are as in CESM's own template; min/max as its
  // "tos:tos_min:min" entries; sum is not used by the template and is unverified.
  const MOM_RED = { A: ["mean", ""], I: [".false.", "_inst"], X: ["max", "_max"], M: ["min", "_min"], SUM: ["sum", "_sum"] };
  function buildOcn(c, rows, meta) {
    const where = {};                                            // name -> module, native preferred
    for (const m of ["ocean_model_rho2", "ocean_model_z", "ocean_model"]) for (const n of (meta.momFields || {})[m] || []) where[n] = m;
    const dropped = [], notes = [], files = {};
    for (const r of rows) {
      if (!MOM_FREQ[r.freq]) { dropped.push({ name: r.name, freq: r.freq, why: `frequency ${r.freq} has no history setting` }); continue; }
      const mod = where[r.name] || "ocean_model";
      if (!where[r.name]) notes.push(r.name);
      const red = MOM_RED[r.method || "A"][0], tail = MOM_RED[r.method || "A"][1];
      ((files[`${r.freq}|${mod}`] ||= { freq: r.freq, mod, fields: [] }).fields).push({ name: r.name, red, tail });
    }
    const keys = Object.keys(files).sort((a, b) => ORDER.indexOf(files[a].freq) - ORDER.indexOf(files[b].freq) || a.localeCompare(b));
    const L = [`# Generated ${meta.date || new Date().toISOString().slice(0, 10)} by the CESM3-CMIP7-output-planner (CMIP7 -> CESM3 variable lists).`,
      `# ${c.file}: ocean history for the selection on the page. ${meta.title || ""}`,
      `# Copy to SourceMods/src.mom/${c.file} in the case. It REPLACES CESM's default diag_table entirely.`,
      ...evidence(meta, "#"),
      ...(notes.length ? [`# ${notes.length} name(s) are not in CESM's diag_table template and go to ocean_model; MOM6 writes them only if it registers them.`] : [])];
    if (!keys.length) return { text: L.concat("# (nothing to export)", tail(rows, dropped, "#")).join("\n") + "\n", dropped };
    const fname = (f) => `"\${CASE}.mom6.h.${f.freq}.${MOM_TAG[f.mod]}.${MOM_FREQ[f.freq][2]}"`;
    L.push("", `"MOM6 diagnostic fields table for CESM case: \${CASE}"`, "1 1 1 0 0 0", "", "### Section-1: File List");
    for (const k of keys) {
      const f = files[k], [[n, u], [nn, nu]] = MOM_FREQ[f.freq];
      L.push(`${fname(f)}, ${n}, "${u}", 1, "days", "time", ${nn}, "${nu}"`);
    }
    L.push("", "### Section-2: Fields List");
    for (const k of keys) {
      const f = files[k];
      L.push(`# ${fname(f)}`);
      const seen = new Set(), lines = [];
      for (const x of f.fields.sort((a, b) => a.name.localeCompare(b.name) || a.tail.localeCompare(b.tail))) {
        let alias = x.name + x.tail;                       // a second method on one field needs its own output name
        if (seen.has(alias)) continue;
        seen.add(alias);
        lines.push([`"${f.mod}",`, `"${x.name}",`, `"${alias}",`, `${fname(f)},`, `"all",`, `"${x.red}",`, `"none",`, "2"]);
      }
      const w = lines[0].map((_, i) => Math.max(...lines.map(l => l[i].length)));   // align the columns within a file
      for (const l of lines) L.push(l.map((t, i) => i < l.length - 1 ? t.padEnd(w[i]) : t).join(" "));
      L.push("");
    }
    return { text: L.concat(tail(rows, dropped, "#")).join("\n") + "\n", dropped };
  }

  // --- validation -----------------------------------------------------------
  // Read the generated text back and check it, so a bug in the generator (or a hand edit) shows up.
  // Returns {errors, warnings}. For CAM/CTSM/MOSART it also checks the round trip: the (name, flag, frequency)
  // lines in the file must be exactly the requested rows minus the reported drops.
  const NL_FREQ = Object.fromEntries(Object.entries(FREQ).map(([f, [n]]) => [n, f]));

  // `key = value` statements of a namelist (continuation lines join the statement before them), comments stripped.
  function statements(text) {
    const out = [];
    for (const raw of text.split("\n")) {
      const line = raw.replace(/!.*$/, "");
      if (!line.trim()) continue;
      const m = line.match(/^\s*([A-Za-z_][\w]*)\s*=\s*(.*)$/);
      if (m) out.push([m[1].toLowerCase(), m[2], m[1]]); else if (out.length) out[out.length - 1][1] += " " + line.trim();
    }
    return out;
  }
  const quoted = (v) => [...v.matchAll(/'([^']*)'/g)].map(m => m[1]);

  function validate(comp, text, rows, dropped, meta = {}) {
    const c = COMPONENTS[comp], errors = [], warnings = [];
    if (!c.ocn) text.split("\n").forEach((l, i) => { if (l.length > 132) errors.push(`line ${i + 1} is ${l.length} characters; Fortran namelist lines must be under 132`); });
    const st = statements(text), get = (k) => (st.find(x => x[0] === k) || [])[1];
    for (const [k, v] of st) if ((v.match(/'/g) || []).length % 2) errors.push(`${k}: unbalanced quotes`);
    if (c.ice) {
      const letters = quoted(get("histfreq") || ""), n = (get("histfreq_n") || "").split(",").length;
      if (letters.length !== 5 || n !== 5) errors.push(`histfreq/histfreq_n must each list 5 streams (found ${letters.length} and ${n})`);
      const valid = new Set(meta.iceFields || []);
      for (const [k, v, orig] of st) if (k.startsWith("f_")) {
        if (valid.size && !valid.has(orig.slice(2))) errors.push(`${k}: not a CICE history field`);
        for (const ch of quoted(v).join("")) if (!letters.includes(ch)) errors.push(`${k}: stream '${ch}' is not in histfreq`);
      }
    } else if (c.glc) {
      const names = (quoted(get("esm_history_vars") || "").join("").split(/\s+/)).filter(Boolean);
      if (new Set(names).size !== names.length) errors.push("esm_history_vars lists a variable twice");
      if (names.length && !Number.isInteger(+get("history_frequency"))) errors.push("history_frequency is not an integer");
    } else if (c.ocn) {
      const files = new Set([...text.matchAll(/^("\$\{CASE\}[^"]*"), \d+, "\w+", 1, "days"/gm)].map(m => m[1])), seen = new Set();
      for (const m of text.matchAll(/^"(\w+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*("[^"]+")\s*,/gm)) {
        if (!files.has(m[4])) errors.push(`field ${m[2]} writes to ${m[4]}, which is not in the file list`);
        if (seen.has(m[4] + m[3])) errors.push(`output name ${m[3]} appears twice in ${m[4]}`);
        seen.add(m[4] + m[3]);
        if (meta.momFields && !(meta.momFields[m[1]] || []).includes(m[2]) && m[1] !== "ocean_model") warnings.push(`${m[2]} is not in ${m[1]}`);
      }
    } else {
      const nh = (get(`${c.pre}nhtfrq`) || "").split(",").map(x => x.trim()).filter(Boolean), n = nh.length;
      for (const k of ["mfilt", ...(c.dov2xy ? ["dov2xy"] : [])]) {
        const len = (get(c.pre + k) || "").split(",").filter(x => x.trim()).length;
        if (len !== n) errors.push(`${c.pre}${k} lists ${len} values but ${c.pre}nhtfrq lists ${n}`);
      }
      if (c.empty && !/\.true\./i.test(get(c.empty) || "")) errors.push(`${c.empty} is not .true.`);
      const got = new Set(), fincl = st.filter(x => x[0].startsWith(c.pre + "fincl"));
      if (fincl.length !== n) errors.push(`${fincl.length} fincl lists for ${n} tapes`);
      for (const [k, v] of fincl) {
        const i = +k.slice((c.pre + "fincl").length), freq = NL_FREQ[nh[i - 1]], seen = new Set();
        if (!(i >= 1 && i <= n)) { errors.push(`${k}: no tape ${i}`); continue; }
        for (const e of quoted(v)) {
          const [name, flag = ""] = e.split(":");
          if (seen.has(name)) errors.push(`${k}: ${name} appears twice on one tape`);
          seen.add(name);
          if (name.length > c.maxName) errors.push(`${k}: ${name} is longer than ${c.maxName} characters`);
          if (flag && !c.flags.includes(flag)) errors.push(`${k}: ${e} has averaging flag ${flag}, not valid for ${comp}`);
          got.add(`${name}|${flag}|${freq}`);
        }
      }
      const gone = new Set(dropped.map(d => `${d.name}|${d.method || ""}|${d.freq}`));
      const want = new Set(rows.map(r => `${r.name}|${r.method || ""}|${r.freq}`).filter(k => !gone.has(k)));
      const show = (a, b) => [...a].filter(x => !b.has(x)).slice(0, 5).map(x => x.replace(/\|/g, " ")).join(", ");
      if (show(want, got)) errors.push(`requested but missing from the file: ${show(want, got)}`);
      if (show(got, want)) errors.push(`in the file but not requested: ${show(got, want)}`);
    }
    return { errors, warnings };
  }

  // rows: [{name, method, freq, items}]  ->  {text, tapes, dropped, validation} | {error}
  function build(comp, rows, meta = {}) {
    const o = buildText(comp, rows, meta);
    if (o.error) return o;
    o.text = wrapComments(o.text);
    o.validation = validate(comp, o.text, rows, o.dropped || [], meta);
    const { errors, warnings } = o.validation, c = COMPONENTS[comp].ocn ? "#" : "!";
    if (errors.length || warnings.length)
      o.text += ["", `${c} --- VALIDATION: ${errors.length} error(s), ${warnings.length} warning(s) ---`,
                 ...errors.map(e => `${c} ERROR: ${e}`), ...warnings.map(w => `${c} warning: ${w}`)].join("\n") + "\n";
    return o;
  }

  function buildText(comp, rows, meta) {
    const c = COMPONENTS[comp];
    if (!c) return { error: `no namelist generator for ${comp}` };
    if (c.glc) return buildGlc(c, rows, meta);
    if (c.ice) return buildIce(c, rows, meta);
    if (c.ocn) return buildOcn(c, rows, meta);
    const dropped = [], byFreq = {};
    for (const r of rows) {
      const why = !FREQ[r.freq] ? `frequency ${r.freq} has no history setting`
        : r.name.length > c.maxName ? `name longer than ${c.maxName} characters`
        : r.method && !c.flags.includes(r.method) ? `averaging flag ${r.method} not valid for ${comp}` : "";
      if (why) { dropped.push({ name: r.name, method: r.method, freq: r.freq, why }); continue; }
      // A name may appear once per tape; a second method at the same frequency opens another tape.
      const tapes = (byFreq[r.freq] ||= []);
      let t = tapes.find(x => !x.names.has(r.name));
      if (!t) tapes.push(t = { freq: r.freq, names: new Set(), entries: [] });
      t.names.add(r.name);
      t.entries.push(r.method ? `${r.name}:${r.method}` : r.name);
    }
    const tapes = ORDER.flatMap(f => byFreq[f] || []);
    if (tapes.length > c.maxTapes) {
      return { error: `${comp} needs ${tapes.length} history tapes (${tapes.map(t => t.freq).join(", ")}); ` +
                      `${c.file} allows ${c.maxTapes}. Drop a frequency.` };
    }
    const L = [...header(c, meta),
               c.empty ? `! ${c.empty} = .true. DISCARDS ${comp}'s default output: only the fields below are written.`
                       : `! ${comp} cannot switch its defaults off: the fields below are ADDED to the model's default output.`,
               ...evidence(meta, "!"),
               `! nhtfrq assumes a 365-day calendar for yr and dec. Unverified by running a case.`];
    if (!tapes.length) return { text: L.concat("! (nothing to export)", tail(rows, dropped, "!")).join("\n") + "\n", tapes, dropped };
    L.push("", "! tape  frequency  nhtfrq  mfilt  fields",
           ...tapes.map((t, i) => `! h${i}`.padEnd(7) + t.freq.padEnd(11) + String(FREQ[t.freq][0]).padEnd(8) + String(FREQ[t.freq][1]).padEnd(7) + t.entries.length));
    L.push("", ...(c.empty ? [` ${c.empty} = .true.`] : []),
           ` ${c.pre}nhtfrq = ${tapes.map(t => FREQ[t.freq][0]).join(", ")}`,
           ` ${c.pre}mfilt = ${tapes.map(t => FREQ[t.freq][1]).join(", ")}`);
    if (c.dov2xy) L.push(` ${c.pre}dov2xy = ${tapes.map(() => ".true.").join(", ")}`);
    tapes.forEach((t, i) => {
      L.push("", `! h${i} -- ${t.freq} (${t.entries.length} fields)`,
             ...pack(` ${c.pre}fincl${i + 1} = `, t.entries.sort().map(q), "    ", ","));
    });
    return { text: L.concat(tail(rows, dropped, "!")).join("\n") + "\n", tapes, dropped };
  }

  // Uncompressed ("stored") zip: [{name, text}] -> Uint8Array. No dependency; CRC-32 is the only arithmetic.
  const CRC = Array.from({ length: 256 }, (_, n) => { for (let k = 0; k < 8; k++) n = n & 1 ? 0xEDB88320 ^ (n >>> 1) : n >>> 1; return n >>> 0; });
  const crc32 = (b) => { let c = ~0; for (const x of b) c = CRC[(c ^ x) & 255] ^ (c >>> 8); return ~c >>> 0; };
  function zip(files, now = new Date()) {
    const enc = new TextEncoder(), parts = [], central = [];
    const dosTime = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
    const dosDate = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
    let offset = 0;
    for (const f of files) {
      const name = enc.encode(f.name), data = enc.encode(f.text), crc = crc32(data);
      const h = new DataView(new ArrayBuffer(30));          // local file header
      [[0, 0x04034b50, 4], [4, 20, 2], [6, 0x0800, 2], [8, 0, 2], [10, dosTime, 2], [12, dosDate, 2], [14, crc, 4],
       [18, data.length, 4], [22, data.length, 4], [26, name.length, 2], [28, 0, 2]].forEach(([o, v, n]) => n == 4 ? h.setUint32(o, v, true) : h.setUint16(o, v, true));
      const e = new DataView(new ArrayBuffer(46));          // central directory entry
      [[0, 0x02014b50, 4], [4, 20, 2], [6, 20, 2], [8, 0x0800, 2], [10, 0, 2], [12, dosTime, 2], [14, dosDate, 2], [16, crc, 4],
       [20, data.length, 4], [24, data.length, 4], [28, name.length, 2], [30, 0, 2], [32, 0, 2], [34, 0, 2], [36, 0, 2],
       [38, 0, 4], [42, offset, 4]].forEach(([o, v, n]) => n == 4 ? e.setUint32(o, v, true) : e.setUint16(o, v, true));
      parts.push(new Uint8Array(h.buffer), name, data);
      central.push(new Uint8Array(e.buffer), name);
      offset += 30 + name.length + data.length;
    }
    const size = central.reduce((n, p) => n + p.length, 0);
    const end = new DataView(new ArrayBuffer(22));
    [[0, 0x06054b50, 4], [8, files.length, 2], [10, files.length, 2], [12, size, 4], [16, offset, 4]]
      .forEach(([o, v, n]) => n == 4 ? end.setUint32(o, v, true) : end.setUint16(o, v, true));
    const all = [...parts, ...central, new Uint8Array(end.buffer)], out = new Uint8Array(offset + size + 22);
    let at = 0; for (const p of all) { out.set(p, at); at += p.length; }
    return out;
  }

  // Every file for a component: the main namelist plus any variants. Errors become an entry the user will see.
  function files(comp, rows, meta) {
    const o = build(comp, rows, meta), c = COMPONENTS[comp];
    if (o.error) return [{ name: `${c.file}.ERROR.txt`, text: o.error + "\n" }];
    return [{ name: c.file, text: o.text }, ...(o.variants || []).map(v => ({ name: `variants/${c.file}.${v.freq}`, text: v.text }))];
  }

  root.Namelist = { build, validate, files, zip, COMPONENTS, FREQ };
  if (typeof module !== "undefined") module.exports = root.Namelist;
})(typeof window !== "undefined" ? window : globalThis);
