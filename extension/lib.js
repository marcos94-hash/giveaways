// Shared logic: entry limits, due status, URL matching, formatting.
// Used by background.js and popup.js (ES module).

export const ET = "America/New_York";
const HOUR = 3600 * 1000;
const ROLLING_BUFFER = 5 * 60 * 1000; // wait 24h + 5 min to be safe

// Wall-clock parts of a timestamp in a given IANA time zone.
export function wallParts(ts, tz) {
  const f = new Intl.DateTimeFormat("en-US", {
    timeZone: tz, hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  const p = {};
  for (const { type, value } of f.formatToParts(new Date(ts))) p[type] = value;
  return { y: +p.year, m: +p.month, d: +p.day, h: +p.hour === 24 ? 0 : +p.hour, mi: +p.minute, s: +p.second };
}

// Which "entry day" a timestamp falls in, for a day that starts at resetHour in tz.
export function periodKey(ts, tz, resetHour = 0) {
  const w = wallParts(ts, tz);
  const shifted = Date.UTC(w.y, w.m - 1, w.d, w.h, w.mi, w.s) - resetHour * HOUR;
  const dt = new Date(shifted);
  return { key: dt.toISOString().slice(0, 10), dow: dt.getUTCDay() };
}

// Next time a new entry day starts after `now`.
function nextReset(now, tz, resetHour, weekdaysOnly) {
  const w = wallParts(now, tz);
  let hoursUntil = (resetHour - w.h + 24) % 24;
  if (hoursUntil === 0) hoursUntil = 24;
  let t = now + hoursUntil * HOUR - w.mi * 60000 - w.s * 1000;
  // Snap after DST shifts: walk forward until the key actually changes.
  const startKey = periodKey(now, tz, resetHour).key;
  let guard = 0;
  while (periodKey(t, tz, resetHour).key === startKey && guard++ < 3) t += HOUR;
  if (weekdaysOnly) {
    guard = 0;
    while (isWeekend(periodKey(t, tz, resetHour).dow) && guard++ < 4) t = nextReset(t, tz, resetHour, false);
  }
  return t;
}

const isWeekend = (dow) => dow === 0 || dow === 6;

// Status of one giveaway given its entry log (array of ms timestamps).
// Returns { state: due|done|waiting|not_started|ended, nextAt?, used, allowed }
export function giveawayStatus(g, entries = [], now = Date.now()) {
  const ends = Date.parse(g.ends);
  const starts = g.starts ? Date.parse(g.starts) : null;
  if (Number.isFinite(ends) && now > ends) return { state: "ended" };
  if (starts && now < starts) return { state: "not_started", nextAt: starts };

  const lim = g.limit || { type: "once" };
  const sorted = [...entries].sort((a, b) => a - b);

  if (lim.type === "once") {
    return sorted.length ? { state: "done", used: 1, allowed: 1, permanent: true } : { state: "due", used: 0, allowed: 1 };
  }

  if (lim.type === "rolling24" || lim.type === "rolling") {
    const hours = lim.type === "rolling" ? Number(lim.hours) || 24 : 24;
    const last = sorted[sorted.length - 1];
    if (!last) return { state: "due", used: 0, allowed: 1 };
    const nextAt = last + hours * HOUR + ROLLING_BUFFER;
    if (now >= nextAt) return { state: "due", used: 0, allowed: 1 };
    return { state: "done", nextAt, used: 1, allowed: 1 };
  }

  if (lim.type === "daily") {
    const tz = lim.reset_tz || ET;
    const rh = lim.reset_hour || 0;
    const count = lim.count || 1;
    const cur = periodKey(now, tz, rh);
    if (lim.weekdays_only && isWeekend(cur.dow)) {
      return { state: "waiting", nextAt: nextReset(now, tz, rh, true), used: 0, allowed: count };
    }
    const used = sorted.filter((t) => periodKey(t, tz, rh).key === cur.key).length;
    if (used < count) return { state: "due", used, allowed: count };
    return { state: "done", nextAt: nextReset(now, tz, rh, !!lim.weekdays_only), used, allowed: count };
  }

  return { state: "due", used: 0, allowed: 1 };
}

// Normalize a URL to host+path without protocol, "www." or trailing slash.
export function normUrl(u) {
  try {
    const x = new URL(u);
    const host = x.host.replace(/^www\./, ""); // keeps a non-default port
    const path = x.pathname.replace(/\/+$/, "");
    return (host + path).toLowerCase();
  } catch {
    return "";
  }
}

// Only real entry pages: https, or http on localhost for testing.
export function schemeAllowed(u) {
  try {
    const x = new URL(u);
    return x.protocol === "https:" || (x.protocol === "http:" && ["localhost", "127.0.0.1"].includes(x.hostname));
  } catch {
    return false;
  }
}

function normPattern(raw) {
  return String(raw || "").trim().toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/+$/, "");
}

// A pattern matches its exact host+path or anything below it at a "/" boundary.
// A trailing "*" opts in to a plain prefix match (e.g. "ign.com/rewards/win-*").
export function patternMatches(n, raw) {
  const p = normPattern(raw);
  if (!p || !n) return false;
  if (p.endsWith("*")) return n.startsWith(p.slice(0, -1));
  return n === p || n.startsWith(p + "/");
}

function entryPatterns(g) {
  return [...(g.match || []), g.entry_url].filter(Boolean);
}

// Is this URL one of the giveaway's entry pages?
export function urlMatches(g, url) {
  if (!schemeAllowed(url)) return false;
  const n = normUrl(url);
  return entryPatterns(g).some((p) => patternMatches(n, p));
}

// May a frame at this URL inside the giveaway's entry page get the profile?
// Same entry pages, or embedded entry providers listed explicitly in g.frames.
export function frameAllowed(g, url) {
  if (!schemeAllowed(url)) return false;
  const n = normUrl(url);
  return [...entryPatterns(g), ...(g.frames || [])].some((p) => patternMatches(n, p));
}

// Find the giveaway whose entry pattern best fits this URL (longest pattern wins).
export function matchGiveaway(url, giveaways) {
  if (!schemeAllowed(url)) return null;
  const n = normUrl(url);
  let best = null, bestLen = 0;
  for (const g of giveaways) {
    for (const raw of entryPatterns(g)) {
      const len = normPattern(raw).length;
      if (patternMatches(n, raw) && len > bestLen) { best = g; bestLen = len; }
    }
  }
  return best;
}

// Ready to enter = the sponsor's own official rules confirmed eligibility, free entry,
// deadline and entry limit. Anything else needs a rules check first.
export function isReady(g) {
  const v = g && g.verification;
  return !!(v && v.status === "verified");
}

export function fmtET(ts) {
  return new Date(ts).toLocaleString("en-US", {
    timeZone: ET, month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  }) + " ET";
}

export function timeLeft(ts, now = Date.now()) {
  const ms = ts - now;
  if (ms <= 0) return "ended";
  const h = ms / HOUR;
  if (h < 1) return `${Math.max(1, Math.round(ms / 60000))} min left`;
  if (h < 48) return `${Math.round(h)} hr left`;
  return `${Math.round(h / 24)} days left`;
}

// Validate a giveaway list fetched from a URL before trusting it.
export function validateList(data) {
  if (!data || !Array.isArray(data.giveaways)) return "Missing a giveaways array.";
  const ok = new Set(["once", "daily", "rolling24", "rolling"]);
  const vs = new Set(["verified", "needs_rules_check"]);
  for (const g of data.giveaways) {
    if (!g.id || !g.name || !g.entry_url || !g.ends) return `Entry missing id, name, entry_url or ends: ${JSON.stringify(g).slice(0, 80)}`;
    if (!/^https?:\/\//.test(g.entry_url)) return `Bad entry_url for ${g.id}`;
    if (!Number.isFinite(Date.parse(g.ends))) return `Bad end date for ${g.id}`;
    if (!g.limit || !ok.has(g.limit.type)) return `Bad limit for ${g.id}`;
    if (g.verification && !vs.has(g.verification.status)) return `Bad verification status for ${g.id}`;
  }
  return null;
}

export function profileComplete(p) {
  return !!(p && p.firstName && p.lastName && p.email);
}

// ---------- eligibility ----------
export function ageFromDob(dob, now = Date.now()) {
  if (!dob || !/^\d{4}-\d{2}-\d{2}$/.test(dob)) return null;
  const [y, m, d] = dob.split("-").map(Number);
  const t = new Date(now);
  let a = t.getFullYear() - y;
  if (t.getMonth() + 1 < m || (t.getMonth() + 1 === m && t.getDate() < d)) a--;
  return a;
}

export function minAge(g) {
  return Number(g.min_age) || (g.flags && g.flags.age21 ? 21 : 18);
}

// false only when we know your age and it's below the giveaway's minimum.
export function isEligible(g, profile, now = Date.now()) {
  const age = ageFromDob(profile && profile.dob, now);
  return age == null || age >= minAge(g);
}

// Giveaways that should show up for you: eligible and not skipped.
export function visibleGiveaways(list, profile, hidden = {}, now = Date.now()) {
  return (list?.giveaways || []).filter((g) => !hidden[g.id] && isEligible(g, profile, now));
}
