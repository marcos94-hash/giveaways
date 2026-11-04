const $ = (id) => document.getElementById(id);
const form = $("profile");

async function load() {
  const { profile = {}, settings = {}, log = {}, list, listSource, listError, listFetchedAt } =
    await chrome.storage.local.get(["profile", "settings", "log", "list", "listSource", "listError", "listFetchedAt"]);
  for (const el of form.elements) if (el.name && profile[el.name] != null) el.value = profile[el.name];
  if (!profile.state) form.elements.state.value = "NJ";
  $("reminderOn").checked = settings.reminderOn !== false;
  $("reminderTime").value = settings.reminderTime || "09:00";
  $("showBanner").checked = settings.showBanner !== false;
  $("listUrl").value = settings.listUrl || "";
  const total = Object.values(log).flat().length;
  $("logSummary").textContent = `${total} entries logged across ${Object.keys(log).filter((k) => log[k].length).length} giveaways.`;
  $("listStatus").textContent = listError ? `Last update failed: ${listError}`
    : listSource && listSource !== "bundled" ? `Using ${listSource} (${list?.giveaways?.length || 0} giveaways${listFetchedAt ? ", fetched " + new Date(listFetchedAt).toLocaleString() : ""})`
    : `Using the built-in list (${list?.giveaways?.length || 0} giveaways, ${list?.updated || ""})`;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const profile = {};
  for (const el of form.elements) if (el.name) profile[el.name] = el.value.trim();
  profile.state = (profile.state || "NJ").toUpperCase();
  profile.phone = profile.phone.replace(/[^\d+]/g, "");
  await chrome.storage.local.set({ profile });
  $("profileSaved").hidden = false;
  setTimeout(() => ($("profileSaved").hidden = true), 2000);
  chrome.runtime.sendMessage({ type: "settingsChanged" });
});

async function saveSettings(extra = {}) {
  const { settings = {} } = await chrome.storage.local.get("settings");
  const next = {
    ...settings,
    reminderOn: $("reminderOn").checked,
    reminderTime: $("reminderTime").value || "09:00",
    showBanner: $("showBanner").checked,
    listUrl: $("listUrl").value.trim(),
    ...extra,
  };
  await chrome.storage.local.set({ settings: next });
  await chrome.runtime.sendMessage({ type: "settingsChanged" });
}

["reminderOn", "reminderTime", "showBanner"].forEach((id) => $(id).addEventListener("change", () => saveSettings()));

$("saveList").addEventListener("click", async () => {
  await saveSettings();
  $("listStatus").textContent = "Refreshing…";
  const r = await chrome.runtime.sendMessage({ type: "refreshList" });
  $("listStatus").textContent = r.ok ? `Loaded ${r.count} giveaways from ${r.source === "bundled" ? "the built-in list" : r.source}.` : `Failed: ${r.error}. Kept the previous list.`;
});

$("exportLog").addEventListener("click", async () => {
  const { log = {}, sources = {}, list } = await chrome.storage.local.get(["log", "sources", "list"]);
  const names = Object.fromEntries((list?.giveaways || []).map((g) => [g.id, g.name]));
  const rows = [["giveaway_id", "giveaway", "logged_at_iso", "how"]];
  for (const [id, ts] of Object.entries(log)) ts.forEach((t, i) => rows.push([id, names[id] || "", new Date(t).toISOString(), (sources[id] || [])[i] || ""]));
  const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = "giveaway_entries.csv";
  a.click();
});

$("clearLog").addEventListener("click", async () => {
  if (!confirm("Clear the whole entry log? The extension will think nothing has been entered today.")) return;
  await chrome.storage.local.set({ log: {}, sources: {} });
  chrome.runtime.sendMessage({ type: "settingsChanged" });
  load();
});

load();
