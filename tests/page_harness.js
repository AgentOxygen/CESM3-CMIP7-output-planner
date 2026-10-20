// Runs docs/index.html's script against docs/data.json with a stubbed DOM; prints a JSON summary. Used by tests/test_page.py.
const fs = require("fs"), vm = require("vm");
const root = require("path").resolve(__dirname, "..", "docs") + "/";
const html = fs.readFileSync(root + "index.html", "utf8");
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const els = {};
const mk = (id) => els[id] ||= { id, innerHTML: "", textContent: "", hidden: false, disabled: false, checked: true, value: "", dataset: {}, children: [],
  setAttribute() {}, addEventListener() {}, insertAdjacentHTML(_, h) { this.innerHTML += h; }, selectedOptions: [{ text: "everything" }], selectedIndex: 0,
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
  out.unconfirmedShown = mk("n-unconfirmed").textContent;
  st.addOnly = true; A.render(); out.only = sum(); out.onlyIcons = icons();
  out.onlyAllExtra = [...A.current.comps.atm.values()].every(r => r.items.every(x => x.extra));
  st.addOnly = false; st.addBoth = true; A.render(); out.both = sum(); out.bothIcons = (main.innerHTML.match(/&#8853;/g) || []).length;
  out.bothCount = mk("n-both").textContent; out.bothAllMarked = [...A.current.comps.atm.values()].every(r => r.simone);
  st.addOnly = true; A.render(); out.union = sum(); st.addBoth = false; st.addOnly = true;
  st.addChem = false; A.render(); out.noChem = sum();
  st.addChem = true; st.addAtm = false; A.render(); out.noAtm = sum();
  st.addAtm = true; st.addOnly = false; chemValue = "MTso"; A.syncChem(); A.render(); out.back = sum(); out.chemOptHiddenAgain = mk("chemOpt").hidden;
  chemValue = "chem"; A.syncChem(); A.render();
  const o = ctx.Namelist.build("atm", [...A.current.comps.atm.values()], { iceFields: [], momFields: {} });
  out.nl = o.error ? { error: o.error } : { freqs: [...new Set(o.tapes.map(t => t.freq))], errors: o.validation.errors };
  console.log(JSON.stringify(out));
})();
