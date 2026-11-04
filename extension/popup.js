import { giveawayStatus, fmtET, timeLeft, profileComplete, isEligible, minAge, isReady } from "./lib.js";

const BATCH = 10;

const $ = (id) => document.getElementById(id);
if (new URLSearchParams(location.search).get("page")) document.body.classList.add("page");

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function chips(g) {
  const out = [];
  const f = g.flags || {};
  if (g.added && Date.now() - Date.parse(g.added) < 3 * 86400000) out.push(`<span class="chip n">new</span>`);
  if (minAge(g) > 18) out.push(`<span class="chip o">${minAge(g)}+</span>`);
  if (f.account) out.push(`<span class="chip" title="${esc(f.account)}">account</span>`);
  if (f.marketing) out.push(`<span class="chip o" title="${esc(f.marketing)}">marketing opt-in</span>`);
  if (g.limit?.type === "once") out.push(`<span class="chip">one entry</span>`);
  if (g.limit?.type === "daily") out.push(`<span class="chip">daily</span>`);
  if (g.limit?.type === "rolling24") out.push(`<span class="chip">every 24 hr</span>`);
  if (g.limit?.type === "rolling") out.push(`<span class="chip">every ${g.limit.hours >= 168 && g.limit.hours % 24 === 0 ? g.limit.hours / 24 + " days" : g.limit.hours + " hr"}</span>`);
  if (isReady(g)) out.push(`<span class="chip n" title="Checked against the sponsor's official rules${g.verification.checked_at ? " on " + esc(g.verification.checked_at.slice(0, 10)) : ""}">rules verified</span>`);
  else out.push(`<span class="chip o" title="${esc(g.verification?.reason || "Not checked against the sponsor's official rules yet")}">needs rules check</span>`);
  return out.join("");
}

function details(g) {
  const v = g.verification || {};
  const bits = [v.status !== "verified" && v.reason ? "Why not verified: " + v.reason : "", g.notes, g.flags?.account, g.flags?.marketing, g.day_note, g.rules_note,
    v.checked_at ? `Last checked ${v.checked_at.slice(0, 16).replace("T", " ")}` : ""].filter(Boolean);
  if (!bits.length) return "";
  return `<details><summary>Details</summary>${bits.map((b) => `<p>${esc(b)}</p>`).join("")}</details>`;
}

function row(g, st, now) {
  const ends = Date.parse(g.ends);
  const soon = ends - now < 48 * 3600 * 1000;
  let meta = `Ends ${fmtET(ends)} · <span class="${soon ? "soon" : ""}">${timeLeft(ends, now)}</span>`;
  if (st.state === "done" && st.nextAt && !st.permanent) meta = `Next entry ${fmtET(st.nextAt)} · ends ${fmtET(ends)}`;
  if (st.state === "done" && st.permanent) meta = `Entered (one entry allowed)`;
  if (st.state === "not_started" || st.state === "waiting") meta = `Opens ${fmtET(st.nextAt)}`;
  const rulesHref = (g.verification && g.verification.rules_source) || g.rules_url;
  const rules = rulesHref ? `<a href="${esc(rulesHref)}" target="_blank">Rules</a>` : "";
  let actions = "";
  if (st.state === "due" && !isReady(g)) {
    actions = `<button data-open="${esc(g.id)}" title="Opens the page. It won't fill until you choose Fill anyway.">Open</button><button data-skip="${esc(g.id)}" class="skip" title="Hide this giveaway">Skip</button>${rules}`;
  } else if (st.state === "due") {
    actions = `<button data-open="${esc(g.id)}">Open</button><button data-mark="${esc(g.id)}" title="Tick only after the site confirmed your entry">✓ Entered</button><button data-skip="${esc(g.id)}" class="skip" title="Hide this giveaway">Skip</button>${rules}`;
  } else if (st.state === "done") {
    actions = `<button data-undo="${esc(g.id)}" title="Remove the last logged entry">Undo</button>${rules}`;
  } else {
    actions = rules;
  }
  return `<div class="row ${st.state}">
    <div class="main">
      <div class="name">${esc(g.name)}</div>
      <div class="prize">${esc(g.prize)}</div>
      <div class="meta">${meta}</div>
      <div class="chips">${chips(g)}</div>
      ${details(g)}
    </div>
    <div class="actions">${actions}</div>
  </div>`;
}

async function render() {
  const { list, log = {}, profile, listSource, listFetchedAt, listError, hidden = {} } = await chrome.storage.local.get(
    ["list", "log", "profile", "listSource", "listFetchedAt", "listError", "hidden"]);
  const all = list?.giveaways || (await chrome.runtime.sendMessage({ type: "getBundled" })).giveaways;
  const now = Date.now();
  const skipped = all.filter((g) => hidden[g.id]).length;
  const tooYoung = all.filter((g) => !hidden[g.id] && !isEligible(g, profile, now) && giveawayStatus(g, [], now).state !== "ended").length;
  const giveaways = all.filter((g) => !hidden[g.id] && isEligible(g, profile, now));
  const rows = giveaways.map((g) => ({ g, st: giveawayStatus(g, log[g.id], now) }));
  const byEnd = (a, b) => Date.parse(a.g.ends) - Date.parse(b.g.ends);
  const due = rows.filter((r) => r.st.state === "due" && isReady(r.g)).sort(byEnd);
  const check = rows.filter((r) => r.st.state === "due" && !isReady(r.g)).sort(byEnd);
  const done = rows.filter((r) => r.st.state === "done").sort(byEnd);
  const later = rows.filter((r) => r.st.state === "not_started" || r.st.state === "waiting").sort((a, b) => a.st.nextAt - b.st.nextAt);

  $("due").innerHTML = due.map((r) => row(r.g, r.st, now)).join("") || `<div class="empty">Nothing ready right now.</div>`;
  $("done").innerHTML = done.map((r) => row(r.g, r.st, now)).join("") || `<div class="empty">None yet today.</div>`;
  $("later").innerHTML = later.map((r) => row(r.g, r.st, now)).join("");
  $("laterSec").hidden = !later.length;
  $("check").innerHTML = check.map((r) => row(r.g, r.st, now)).join("");
  $("checkSec").hidden = !check.length;
  $("checkCount").textContent = `(${check.length})`;
  $("dueCount").textContent = `(${due.length})`;
  $("doneCount").textContent = `(${done.length})`;
  $("summary").textContent = `${due.length} ready · ${done.length} done · ${check.length} need a rules check`;

  const btn = $("openAll");
  btn.disabled = !due.length || !profileComplete(profile);
  btn.textContent = !due.length ? "All caught up" : due.length > BATCH ? `Open next ${BATCH} of ${due.length}` : `Open all ${due.length} due`;
  btn.onclick = () => chrome.runtime.sendMessage({ type: "openGiveaways", ids: due.slice(0, BATCH).map((r) => r.g.id) });

  const warn = $("warn");
  if (!profileComplete(profile)) {
    warn.hidden = false;
    warn.innerHTML = `Add your name and email in <a href="options.html" target="_blank">Settings</a> before opening entries.`;
  } else if (listError) {
    warn.hidden = false;
    warn.textContent = `List update failed: ${listError}`;
  } else warn.hidden = true;

  const weekAgo = now - 7 * 86400000;
  const week = Object.values(log).flat().filter((t) => t > weekAgo).length;
  const src = listSource && listSource !== "bundled" ? `list from ${new URL(listSource).host}${listFetchedAt ? ", updated " + fmtET(listFetchedAt) : ""}` : `built-in list (${list?.updated || ""})`;
  const extras = [skipped ? `${skipped} skipped` : "", tooYoung ? `${tooYoung} hidden (age limit)` : ""].filter(Boolean).join(" · ");
  $("foot").innerHTML = `${week} entries logged in the last 7 days · ${src}${extras ? "<br>" + extras : ""}${skipped ? ' · <a href="#" id="unskip">show skipped</a>' : ""}`;
  const un = document.getElementById("unskip");
  if (un) un.onclick = async (e) => { e.preventDefault(); await chrome.runtime.sendMessage({ type: "unskip" }); render(); };

  document.querySelectorAll("[data-open]").forEach((b) => b.onclick = () => chrome.runtime.sendMessage({ type: "openGiveaways", ids: [b.dataset.open] }));
  document.querySelectorAll("[data-mark]").forEach((b) => b.onclick = async () => { await chrome.runtime.sendMessage({ type: "markEntered", id: b.dataset.mark, source: "popup" }); render(); });
  document.querySelectorAll("[data-skip]").forEach((b) => b.onclick = async () => { await chrome.runtime.sendMessage({ type: "skip", id: b.dataset.skip }); render(); });
  document.querySelectorAll("[data-undo]").forEach((b) => b.onclick = async () => { await chrome.runtime.sendMessage({ type: "undoEntered", id: b.dataset.undo }); render(); });
}

chrome.storage.onChanged.addListener((c) => { if (c.log || c.list || c.profile || c.hidden) render(); });
render();
// Pick up a list the daily review just wrote to disk.
chrome.runtime.sendMessage({ type: "refreshList" }).catch(() => {});
