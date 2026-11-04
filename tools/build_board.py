#!/usr/bin/env python3
"""Build data/board.html (the Giveaway Board artifact) from data/giveaways.json."""
import json
import os

import reviewlib as R

data = R.load("giveaways.json", {"giveaways": []})
log = R.load_log()
cands = R.load("candidates.json", {"candidates": {}})
gs = data["giveaways"]
counts = R.counts(log, data, cands.get("candidates", {}))
rl = counts["review_log"]
payload = {
    "giveaways": [{k: g.get(k) for k in ("id", "name", "prize", "category", "entry_url", "rules_url", "rules_note", "ends",
                                         "starts", "limit", "min_age", "flags", "notes", "added", "verification")} for g in gs],
    "updated": data.get("updated"),
    "built": R.now().strftime("%b %-d, %-I:%M %p ET"),
    "found": cands.get("count", 0),
    "rejected": rl.get("rejected", 0),
    "waiting": counts["new_waiting"] + rl.get("blocked", 0) + rl.get("needs_review", 0),
}

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Giveaway Board</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
<style>
:root {
  /* Layout: summary strip, filter chips, then one ticket-like row per giveaway sorted by deadline. */
  --bg: #f4f6f3; --surface: #ffffff; --ink: #14201a; --muted: #5d6b63; --line: #dde3dd;
  --accent: #157a46; --accent-soft: #e2f2e8; --warn: #b54708; --warn-soft: #fdf0e3; --hot: #b42318;
  --display: "Bricolage Grotesque", "Avenir Next", system-ui, sans-serif;
  --body: "IBM Plex Sans", -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, monospace;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f1512; --surface: #161e1a; --ink: #e6ede8; --muted: #95a39b; --line: #26322c;
    --accent: #4cc68a; --accent-soft: #173226; --warn: #f2a65a; --warn-soft: #33261a; --hot: #f97066;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0f1512; --surface: #161e1a; --ink: #e6ede8; --muted: #95a39b; --line: #26322c;
  --accent: #4cc68a; --accent-soft: #173226; --warn: #f2a65a; --warn-soft: #33261a; --hot: #f97066;
  color-scheme: dark;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.45 var(--body); }
main { max-width: 900px; margin: 0 auto; padding: 28px 16px 48px; display: grid; gap: 18px; }
h1 { font: 700 30px/1.1 var(--display); margin: 0; text-wrap: balance; letter-spacing: -0.01em; }
.sub { color: var(--muted); margin-top: 4px; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.stat { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; }
.stat b { display: block; font: 700 24px/1.1 var(--display); font-variant-numeric: tabular-nums; }
.stat span { color: var(--muted); font-size: 12px; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.filters button { font: 500 13px var(--body); color: var(--ink); background: var(--surface); border: 1px solid var(--line);
  border-radius: 999px; padding: 5px 12px; cursor: pointer; }
.filters button[aria-pressed="true"] { background: var(--ink); color: var(--bg); border-color: var(--ink); }
.filters button:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.filters label { color: var(--muted); font-size: 13px; display: flex; gap: 6px; align-items: center; margin-left: auto; }
.list { display: grid; gap: 10px; }
.row { background: var(--surface); border: 1px solid var(--line); border-left: 5px solid var(--line); border-radius: 10px;
  padding: 12px 14px; display: grid; grid-template-columns: 1fr auto; gap: 6px 16px; }
.row.soon { border-left-color: var(--hot); }
.row.week { border-left-color: var(--warn); }
.row.later { border-left-color: var(--accent); }
.prize { font: 600 16px/1.3 var(--display); }
.name { color: var(--muted); font-size: 13px; }
.when { text-align: right; font-family: var(--mono); font-size: 13px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.when .left { display: block; font-family: var(--body); font-size: 12px; color: var(--muted); }
.soon .when .left { color: var(--hot); font-weight: 600; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; grid-column: 1 / -1; }
.chip { font-size: 12px; border-radius: 999px; padding: 1px 8px; background: var(--bg); border: 1px solid var(--line); color: var(--ink); }
.chip.new { background: var(--accent-soft); border-color: transparent; color: var(--accent); font-weight: 600; }
.chip.warn { background: var(--warn-soft); border-color: transparent; color: var(--warn); }
.notes { grid-column: 1 / -1; color: var(--muted); font-size: 13px; max-width: 70ch; }
.links { grid-column: 1 / -1; display: flex; gap: 14px; font-size: 13px; }
.links a { color: var(--accent); font-weight: 600; text-decoration: none; }
.links a:hover { text-decoration: underline; }
.empty { color: var(--muted); padding: 20px 0; }
.sec { font: 700 18px/1.2 var(--display); margin: 8px 0 0; }
.sec span { color: var(--muted); font-weight: 600; }
.secnote { color: var(--muted); font-size: 13px; margin: -10px 0 0; max-width: 70ch; }
.row.check { border-left-color: var(--warn); border-left-style: dashed; }
.why { grid-column: 1 / -1; font-size: 13px; color: var(--warn); max-width: 70ch; }
footer { color: var(--muted); font-size: 12px; max-width: 70ch; }
@media (max-width: 560px) { .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } .row { grid-template-columns: 1fr; } .when { text-align: left; } }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>
<main>
  <header>
    <h1>Giveaway Board</h1>
    <div class="sub" id="sub"></div>
  </header>
  <section class="stats" id="stats" aria-label="Summary"></section>
  <section class="filters" aria-label="Filters">
    <button type="button" data-cat="all" aria-pressed="true" id="f-all">All</button>
    <button type="button" data-cat="cash" aria-pressed="false" id="f-cash">Cash</button>
    <button type="button" data-cat="gift_card" aria-pressed="false" id="f-gift">Gift cards</button>
    <button type="button" data-cat="electronics" aria-pressed="false" id="f-elec">Electronics</button>
    <button type="button" data-cat="other" aria-pressed="false" id="f-other">Everything else</button>
    <label for="daily"><input type="checkbox" id="daily"> Daily entries only</label>
  </section>
  <h2 class="sec">Ready to enter <span id="readyCount"></span></h2>
  <p class="secnote">Checked against the sponsor's own official rules: eligibility, free entry, deadline and entry limit.</p>
  <section class="list" id="list" aria-label="Ready to enter"></section>
  <h2 class="sec">Needs a rules check <span id="checkCount"></span></h2>
  <p class="secnote">Found and partly checked, but not yet confirmed against the sponsor's own rules. Read the rules before entering; the extension won't fill these on its own.</p>
  <section class="list" id="checklist" aria-label="Needs a rules check"></section>
  <footer id="foot"></footer>
</main>
<script>
const DATA = __DATA__;
const DAY = 86400000;
const fmt = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const now = Date.now();
const live = DATA.giveaways.filter((g) => Date.parse(g.ends) > now).sort((a, b) => Date.parse(a.ends) - Date.parse(b.ends));
let cat = "all";

function limitText(l) {
  if (!l) return "";
  if (l.type === "once") return "One entry";
  if (l.type === "daily") return l.count > 1 ? `${l.count} a day` : (l.weekdays_only ? "Daily, weekdays" : "Daily");
  if (l.type === "rolling24") return "Every 24 hr";
  if (l.type === "rolling") return l.hours % 24 === 0 ? `Every ${l.hours / 24} days` : `Every ${l.hours} hr`;
  return l.type;
}
function left(ms) {
  if (ms < 3600000) return "under an hour left";
  if (ms < 2 * DAY) return `${Math.round(ms / 3600000)} hr left`;
  return `${Math.round(ms / DAY)} days left`;
}
const isDaily = (g) => g.limit && g.limit.type !== "once";
const isReady = (g) => !!(g.verification && g.verification.status === "verified");
const group = (g) => ["cash", "gift_card", "electronics"].includes(g.category) ? g.category : "other";

function card(g) {
    const ms = Date.parse(g.ends) - now;
    const band = ms < 2 * DAY ? "soon" : ms < 7 * DAY ? "week" : "later";
    const chips = [];
    if (g.added && now - Date.parse(g.added + "T12:00:00-05:00") < 3 * DAY) chips.push('<span class="chip new">New</span>');
    chips.push(`<span class="chip">${esc(limitText(g.limit))}</span>`);
    if ((g.min_age || 18) > 18) chips.push(`<span class="chip warn">${g.min_age}+</span>`);
    if (g.flags && g.flags.account) chips.push(`<span class="chip" title="${esc(g.flags.account)}">Account needed</span>`);
    if (g.flags && g.flags.marketing) chips.push(`<span class="chip warn" title="${esc(g.flags.marketing)}">Marketing opt-in</span>`);
    const v = g.verification || {};
    if (isReady(g)) chips.push(`<span class="chip new">Rules verified ${esc((v.checked_at || "").slice(0, 10))}</span>`);
    else chips.push(`<span class="chip warn">Needs rules check</span>`);
    const href = v.rules_source || g.rules_url;
    const rules = href ? `<a href="${esc(href)}" target="_blank" rel="noopener">Official rules</a>` : (g.rules_note ? `<span class="name">${esc(g.rules_note)}</span>` : "");
    const why = !isReady(g) && v.reason ? `<div class="why">Why not verified: ${esc(v.reason)}</div>` : "";
    return `<article class="row ${isReady(g) ? band : "check"}">
      <div><div class="prize">${esc(g.prize)}</div><div class="name">${esc(g.name)}</div></div>
      <div class="when">${esc(fmt.format(new Date(g.ends)))} ET<span class="left">${left(ms)}</span></div>
      <div class="chips">${chips.join("")}</div>
      ${why}
      ${g.notes ? `<div class="notes">${esc(g.notes)}</div>` : ""}
      <div class="links"><a href="${esc(g.entry_url)}" target="_blank" rel="noopener">Entry page</a>${rules}</div>
    </article>`;
}

function render() {
  const daily = document.getElementById("daily").checked;
  const rows = live.filter((g) => (cat === "all" || group(g) === cat) && (!daily || isDaily(g)));
  const ready = rows.filter(isReady), check = rows.filter((g) => !isReady(g));
  document.getElementById("list").innerHTML = ready.map(card).join("") || '<div class="empty">Nothing ready in this filter right now.</div>';
  document.getElementById("checklist").innerHTML = check.map(card).join("") || '<div class="empty">Nothing waiting on a rules check in this filter.</div>';
  document.getElementById("readyCount").textContent = `(${ready.length})`;
  document.getElementById("checkCount").textContent = `(${check.length})`;
}

document.getElementById("sub").textContent = `Free giveaways for an adult New Jersey resident. Ready ones are checked against the sponsor's own official rules. Updated ${DATA.built}.`;
const weekCount = live.filter((g) => Date.parse(g.ends) - now < 7 * DAY).length;
document.getElementById("stats").innerHTML = [
  [live.filter(isReady).length, "ready to enter"], [live.filter((g) => !isReady(g)).length, "need a rules check"],
  [weekCount, "end within 7 days"], [DATA.waiting, "still in the review queue"],
].map(([n, l]) => `<div class="stat"><b>${n}</b><span>${l}</span></div>`).join("");
document.getElementById("foot").textContent = `The Mac mini scans listing sites twice a day (${DATA.found} found). Claude reads each new giveaway's official rules: ${DATA.rejected} turned down so far, ${DATA.waiting} still waiting or being retried. Enter with the Giveaway Filler extension: it fills ready giveaways, you submit. 21+ giveaways are hidden in the extension if your birth date says you're under 21.`;
document.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => {
  cat = b.dataset.cat;
  document.querySelectorAll("[data-cat]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  render();
}));
document.getElementById("daily").addEventListener("change", render);
render();
</script>
</body>
</html>
"""

out = PAGE.replace("__DATA__", json.dumps(payload).replace("</", "<\\/"))
path = os.path.join(R.DATA, "board.html")
with open(path, "w") as f:
    f.write(out)
print(path, f"{len(gs)} giveaways")
