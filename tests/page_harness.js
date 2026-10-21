// Runs docs/index.html's script against docs/data.json with a stubbed DOM; prints a JSON summary. Used by tests/test_page.py.
const fs = require("fs"), vm = require("vm");
const root = require("path").resolve(__dirname, "..", "docs") + "/";
const html = fs.readFileSync(root + "index.html", "utf8");
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const els = {};
const mk = (id) => els[id] ||= { id, innerHTML: "", textContent: "", hidden: false, disabled: false, checked: true, value: "", dataset: {}, children: [],
  setAttribute(k, v) { (this.attrs ||= {})[k] = v; }, addEventListener(t, f) { (this.on ||= {})[t] = f; }, insertAdjacentHTML(_, h) { this.innerHTML += h; }, selectedOptions: [{ text: "everything" }], selectedIndex: 0,
  closest() { return null; }, scrollIntoView() {} };
let chemValue = "MTso";
const document = { getElementById: mk, body: { addEventListener() {} },
  querySelectorAll: () => [{ addEventListener() {} }],
  querySelector: (q) => q.includes("chem") ? { value: chemValue } : mk(q) };
const ctx = { document, location: { search: "", hostname: "x", pathname: "/" }, URLSearchParams, setInterval() {}, console, Set, Map, Math, Object, Array, JSON, String, Number, Promise,
  fetch: () => Promise.resolve({ json: () => Promise.resolve(JSON.parse(fs.readFileSync(root + "data.json", "utf8"))) }),
  URL, Blob: class {}, alert() {}, window: undefined };
ctx.Namelist = require(root + "namelist.js");
vm.createContext(ctx);
vm.runInContext(code + "\n;globalThis.__api = { state, render, compute, get current() { return current; }, B: () => B, syncChem: typeof syncChem === 'function' ? syncChem : null };", ctx);
(async () => {
  await new Promise(r => setTimeout(r, 50));
  const A = ctx.__api, st = A.state, main = mk("main"), out = {};
  const sum = () => Object.fromEntries(Object.entries(A.current.comps).map(([k, v]) => [k, v.size]));
  const icons = () => (main.innerHTML.match(/class="sym s-extra"/g) || []).length;
  st.exp = process.argv[2] || "piControl";
  A.render(); out.mtso = sum(); out.mtsoIcons = icons();
  chemValue = "chem"; A.syncChem(); A.render(); out.mt4s = sum(); out.mt4sIcons = icons();
  out.chemOptHidden = mk("chemOpt").hidden; out.addAtmDisabled = mk("addAtm").disabled;
  st.addExtra = false; A.render(); out.noExtra = sum();
  st.addExtra = true; const keepSt = st.st; st.st = new Set(); A.render(); out.only = sum(); out.onlyIcons = icons();   // no mapping box ticked: additional variables alone
  out.onlyAllExtra = [...A.current.comps.atm.values()].every(r => r.items.every(x => x.extra));
  st.addChem = false; A.render(); out.noChem = sum();
  st.addChem = true; st.addAtm = false; A.render(); out.noAtm = sum();
  st.st = keepSt;
  st.addAtm = true; chemValue = "MTso"; A.syncChem(); A.render(); out.back = sum(); out.chemOptHiddenAgain = mk("chemOpt").hidden;
  chemValue = "chem"; A.syncChem(); A.render();
  out.pies = (mk("charts").innerHTML.match(/class="pie"/g) || []).length;
  const ch = mk("charts"), btn = mk("chartsBtn"); ch.hidden = true;   // as in the markup
  btn.on.click(); out.chartsOpen = { hidden: ch.hidden, aria: btn.attrs["aria-expanded"], text: btn.innerHTML };
  btn.on.click(); out.chartsShut = { hidden: ch.hidden, aria: btn.attrs["aria-expanded"], text: btn.innerHTML };
  const live = () => ({ tot: mk("tot").textContent, zipDisabled: mk("zip").disabled, charts: mk("charts").innerHTML,
    checked: (main.innerHTML.match(/data-comp="(\w+)" checked/g) || []).length, boxes: (main.innerHTML.match(/data-comp=/g) || []).length });
  out.compAll = live();
  st.offComp.add("atm"); A.render(); out.compNoAtm = live(); out.compNoAtmHtml = /data-comp="atm"\s+title/.test(main.innerHTML);
  for (const c of A.B().components) st.offComp.add(c); A.render(); out.compNone = live();
  st.offComp.clear(); A.render(); out.compBack = live();
  const o = ctx.Namelist.build("atm", [...A.current.comps.atm.values()], { iceFields: [], momFields: {} });
  out.nl = o.error ? { error: o.error } : { freqs: [...new Set(o.tapes.map(t => t.freq))], errors: o.validation.errors };
  console.log(JSON.stringify(out));
})();
