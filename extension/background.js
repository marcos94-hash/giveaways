// Giveaway Filler background service worker.
// Keeps the giveaway list, the entry log, the badge and reminders, and decides which
// pages and frames may receive your saved details. It never submits anything, and it
// only logs an entry when you confirm it went through.

import {
  giveawayStatus, matchGiveaway, urlMatches, frameAllowed, validateList, profileComplete,
  isEligible, visibleGiveaways, minAge, isReady,
} from "./lib.js";

// Daily-reviewed list published by the review task (GitHub). Empty = built-in list only.
const DEFAULT_LIST_URL = "https://raw.githubusercontent.com/marcos94-hash/giveaways/main/data/giveaways.json";

const DEFAULT_SETTINGS = {
  listUrl: "",
  reminderOn: true,
  reminderTime: "09:00",
  showBanner: true,
};

// ---------- storage helpers ----------
async function get(keys) { return chrome.storage.local.get(keys); }
async function set(obj) { return chrome.storage.local.set(obj); }

async function bundledList() {
  const res = await fetch(chrome.runtime.getURL("giveaways.json"));
  return res.json();
}

async function getList() {
  const { list } = await get("list");
  if (list && Array.isArray(list.giveaways)) return list;
  const b = await bundledList();
  await set({ list: b, listSource: "bundled" });
  return b;
}

async function getSettings() {
  const { settings } = await get("settings");
  return { ...DEFAULT_SETTINGS, ...(settings || {}) };
}

async function getLog() {
  const { log } = await get("log");
  return log || {};
}

// Session-only tab state. tabMap is just a hint for which giveaway a tab was opened for;
// it never authorizes anything on its own. overrides = "Fill anyway" for one page.
async function getSession() {
  const { tabMap = {}, overrides = {} } = await chrome.storage.session.get(["tabMap", "overrides"]);
  return { tabMap, overrides };
}
async function setSession(obj) { return chrome.storage.session.set(obj); }

function active(list, now = Date.now()) {
  return list.giveaways.filter((g) => giveawayStatus(g, [], now).state !== "ended");
}

// ---------- list refresh ----------
async function refreshList() {
  const settings = await getSettings();
  const url = settings.listUrl || (DEFAULT_LIST_URL.startsWith("http") ? DEFAULT_LIST_URL : "");
  if (!url) {
    const b = await bundledList();
    await set({ list: b, listSource: "bundled", listError: "" });
    await updateBadge();
    return { ok: true, source: "bundled", count: b.giveaways.length };
  }
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const err = validateList(data);
    if (err) throw new Error(err);
    await set({ list: data, listSource: url, listFetchedAt: Date.now(), listError: "" });
    await updateBadge();
    return { ok: true, source: url, count: data.giveaways.length };
  } catch (e) {
    const { list } = await get("list");
    if (!list) { const b = await bundledList(); await set({ list: b, listSource: "bundled" }); }
    await set({ listError: `${e.message} (kept the previous list)` });
    return { ok: false, error: e.message };
  }
}

// ---------- badge + reminders (ready-to-enter giveaways only) ----------
async function dueGiveaways() {
  const [list, log] = [await getList(), await getLog()];
  const { profile, hidden } = await get(["profile", "hidden"]);
  const now = Date.now();
  return visibleGiveaways(list, profile, hidden || {}, now)
    .filter((g) => isReady(g) && giveawayStatus(g, log[g.id], now).state === "due");
}

async function updateBadge() {
  const due = await dueGiveaways();
  await chrome.action.setBadgeBackgroundColor({ color: due.length ? "#c2410c" : "#15803d" });
  await chrome.action.setBadgeText({ text: due.length ? String(due.length) : "" });
}

function nextTimeToday(hhmm) {
  const [h, m] = (hhmm || "09:00").split(":").map(Number);
  const d = new Date();
  d.setHours(h, m, 0, 0);
  if (d.getTime() <= Date.now()) d.setDate(d.getDate() + 1);
  return d.getTime();
}

async function scheduleAlarms() {
  const s = await getSettings();
  await chrome.alarms.clearAll();
  chrome.alarms.create("badge", { periodInMinutes: 15 });
  chrome.alarms.create("refresh", { periodInMinutes: 60 });
  if (s.reminderOn) chrome.alarms.create("reminder", { when: nextTimeToday(s.reminderTime), periodInMinutes: 1440 });
}

chrome.alarms.onAlarm.addListener(async (a) => {
  if (a.name === "badge") return updateBadge();
  if (a.name === "refresh") return refreshList();
  if (a.name === "reminder") {
    const due = await dueGiveaways();
    if (!due.length) return;
    chrome.notifications.create("giveaway-reminder", {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: `${due.length} giveaway${due.length > 1 ? "s" : ""} ready to enter`,
      message: "Click to see today's list.",
      priority: 1,
    });
  }
});

chrome.notifications.onClicked.addListener(() => {
  chrome.tabs.create({ url: chrome.runtime.getURL("popup.html?page=1") });
});

// ---------- entry log (only on your explicit confirmation) ----------
async function markEntered(id, source) {
  const log = await getLog();
  const list = await getList();
  const g = list.giveaways.find((x) => x.id === id);
  if (!g) return { ok: false, error: "Unknown giveaway" };
  const st = giveawayStatus(g, log[id]);
  if (st.state !== "due") return { ok: false, already: true, status: st };
  log[id] = [...(log[id] || []), Date.now()];
  const { sources } = await get("sources");
  const src = sources || {};
  src[id] = [...(src[id] || []), source].slice(-200);
  await set({ log, sources: src });
  await updateBadge();
  return { ok: true, status: giveawayStatus(g, log[id]) };
}

async function undoEntered(id) {
  const log = await getLog();
  if (!log[id] || !log[id].length) return { ok: false };
  log[id] = log[id].slice(0, -1);
  await set({ log });
  await updateBadge();
  return { ok: true };
}

// ---------- tabs ----------
async function openGiveaways(ids) {
  const list = await getList();
  const { tabMap } = await getSession();
  let first = true;
  for (const id of ids) {
    const g = list.giveaways.find((x) => x.id === id);
    if (!g) continue;
    const tab = await chrome.tabs.create({ url: g.entry_url, active: first });
    first = false;
    tabMap[tab.id] = id;
  }
  await setSession({ tabMap });
}

// The giveaway whose entry pages include this top-level URL. The URL is what authorizes;
// the tab hint only breaks ties between overlapping giveaways.
async function giveawayForPage(tabId, topUrl) {
  const list = await getList();
  const live = active(list);
  const { tabMap } = await getSession();
  const hinted = live.find((g) => g.id === tabMap[tabId]);
  if (hinted && urlMatches(hinted, topUrl)) return hinted;
  return matchGiveaway(topUrl, live);
}

// "Fill anyway" lasts for one page load. Tab hints are dropped when the tab leaves the
// giveaway's entry pages.
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  if (!changeInfo.url && changeInfo.status !== "loading") return;
  const { tabMap, overrides } = await getSession();
  let changed = false;
  if (overrides[tabId]) { delete overrides[tabId]; changed = true; }
  if (changeInfo.url && tabMap[tabId]) {
    const list = await getList();
    const g = list.giveaways.find((x) => x.id === tabMap[tabId]);
    if (!g || !urlMatches(g, changeInfo.url)) { delete tabMap[tabId]; changed = true; }
  }
  if (changed) await setSession({ tabMap, overrides });
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const { tabMap, overrides } = await getSession();
  if (tabMap[tabId] || overrides[tabId]) {
    delete tabMap[tabId]; delete overrides[tabId];
    await setSession({ tabMap, overrides });
  }
});

// Decide what a content script in a given frame may have.
async function decide(sender) {
  const tab = sender.tab;
  if (!tab) return { fill: false };
  const topUrl = sender.frameId === 0 ? sender.url : tab.url;
  const g = await giveawayForPage(tab.id, topUrl);
  if (!g) return { fill: false };
  const frameOk = sender.frameId === 0 ? urlMatches(g, sender.url) : frameAllowed(g, sender.url);
  if (!frameOk) return { fill: false };

  const { profile } = await get("profile");
  const settings = await getSettings();
  const log = await getLog();
  const base = { giveaway: { id: g.id, name: g.name }, showBanner: settings.showBanner, ready: isReady(g) };
  if (!isEligible(g, profile)) return { ...base, fill: false, ineligible: true, minAge: minAge(g) };
  const status = giveawayStatus(g, log[g.id]);
  // Details are released only while an entry is actually allowed right now.
  if (status.state === "done") return { ...base, fill: false, status };
  if (status.state !== "due") return { ...base, fill: false, notOpen: true, status };
  if (!profileComplete(profile)) return { ...base, fill: false, needsProfile: true, status };
  if (!base.ready) {
    const { overrides } = await getSession();
    const o = overrides[tab.id];
    const overridden = o && o.id === g.id && o.url === tab.url;
    if (!overridden) {
      return { ...base, fill: false, needsCheck: true, status,
               reason: (g.verification && g.verification.reason) || "The sponsor's official rules haven't been checked yet." };
    }
  }
  return { ...base, fill: true, status, profile };
}

// ---------- messages ----------
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    switch (msg.type) {
      case "shouldFill": return reply(await decide(sender));
      case "fillAnyway": {
        // Only from the top frame of a page that is one of the giveaway's entry pages.
        if (!sender.tab || sender.frameId !== 0) return reply({ ok: false });
        const g = await giveawayForPage(sender.tab.id, sender.url);
        if (!g || !urlMatches(g, sender.url)) return reply({ ok: false });
        const { overrides } = await getSession();
        overrides[sender.tab.id] = { id: g.id, url: sender.tab.url };
        await setSession({ overrides });
        chrome.tabs.sendMessage(sender.tab.id, { type: "refill" }).catch(() => {});
        return reply({ ok: true });
      }
      case "frameFilled": {
        if (sender.tab && sender.frameId !== 0) {
          chrome.tabs.sendMessage(sender.tab.id, { type: "childFilled", count: msg.count }, { frameId: 0 }).catch(() => {});
        }
        return reply({ ok: true });
      }
      case "frameSubmitAttempt": {
        if (sender.tab && sender.frameId !== 0) {
          chrome.tabs.sendMessage(sender.tab.id, { type: "submitAttempt" }, { frameId: 0 }).catch(() => {});
        }
        return reply({ ok: true });
      }
      case "markEntered": {
        let id = msg.id;
        if (!id && sender.tab) {
          const topUrl = sender.frameId === 0 ? sender.url : sender.tab.url;
          id = (await giveawayForPage(sender.tab.id, topUrl))?.id;
        }
        const r = id ? await markEntered(id, msg.source || "manual") : { ok: false };
        if (r.ok && sender.tab) chrome.tabs.sendMessage(sender.tab.id, { type: "recheck" }).catch(() => {});
        return reply(r);
      }
      case "undoEntered": return reply(await undoEntered(msg.id));
      case "skip": case "unskip": {
        const { hidden = {} } = await get("hidden");
        if (msg.type === "skip") hidden[msg.id] = Date.now(); else if (msg.id) delete hidden[msg.id]; else Object.keys(hidden).forEach((k) => delete hidden[k]);
        await set({ hidden });
        await updateBadge();
        return reply({ ok: true });
      }
      case "openGiveaways": await openGiveaways(msg.ids || []); return reply({ ok: true });
      case "refreshList": return reply(await refreshList());
      case "settingsChanged": await scheduleAlarms(); await updateBadge(); return reply({ ok: true });
      case "getBundled": return reply(await bundledList());
      default: return reply({ ok: false, error: "unknown message" });
    }
  })();
  return true; // async reply
});

chrome.runtime.onInstalled.addListener(async () => {
  const { settings } = await get("settings");
  if (!settings) await set({ settings: DEFAULT_SETTINGS });
  await refreshList();
  await scheduleAlarms();
  await updateBadge();
  const { profile } = await get("profile");
  if (!profileComplete(profile)) chrome.runtime.openOptionsPage();
});

chrome.runtime.onStartup.addListener(async () => {
  await scheduleAlarms();
  await refreshList();
  await updateBadge();
});
