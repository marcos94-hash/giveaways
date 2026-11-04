// End-to-end test: loads the real extension in Chromium and runs it against local test pages.
// Run from this folder: python3 server.py site /tmp/gf_server.log &  then  node test_extension.mjs
import fs from "node:fs";
import path from "node:path";

let pw;
try { pw = (await import("playwright")).default; } catch { pw = (await import("/opt/npm-tools/node_modules/playwright/index.js")).default; }
const { chromium } = pw;
const SRC_EXT = path.resolve("../extension");
const EXT = fs.mkdtempSync("/tmp/gf-ext-");
fs.cpSync(SRC_EXT, EXT, { recursive: true });
// The test machine can't reach GitHub, so test the on-disk list path.
{ const bg = path.join(EXT, "background.js"); fs.writeFileSync(bg, fs.readFileSync(bg, "utf8").replace(/const DEFAULT_LIST_URL = ".*?";/, 'const DEFAULT_LIST_URL = "";')); }

const SITE = "http://localhost:8123";
const LOG = "/tmp/gf_server.log";
const results = [];
const check = (name, cond, detail = "") => { results.push({ name, pass: !!cond, detail }); console.log(`${cond ? "PASS" : "FAIL"} - ${name}${detail ? "  (" + detail + ")" : ""}`); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const requests = () => fs.existsSync(LOG) ? fs.readFileSync(LOG, "utf8") : "";
const bannerText = (p) => p.evaluate(() => document.getElementById("giveaway-filler-banner")?.shadowRoot?.textContent || "");
const bannerClick = (p, id) => p.evaluate((id) => document.getElementById("giveaway-filler-banner").shadowRoot.querySelector(`[data-id="${id}"]`)?.click(), id);

const VER = { status: "verified", rules_source: `${SITE}/rules`, checked_at: "2026-11-04T00:00:00-05:00",
  confirmed: { eligibility: true, free_entry: true, deadline: true, entry_limit: true } };
const far = "2027-06-01T00:00:00-04:00";
const daily = { type: "daily", count: 1, reset_tz: "America/New_York", reset_hour: 0 };
const testList = { version: 1, updated: "test", giveaways: [
  { id: "t-form", name: "Test form", prize: "$5,000", entry_url: `${SITE}/form.html`, match: ["localhost:8123/form.html"], ends: far, limit: daily, flags: {}, verification: VER },
  { id: "t-late", name: "Late form", prize: "$1", entry_url: `${SITE}/late.html`, ends: far, limit: daily, flags: {}, verification: VER },
  { id: "t-iframe", name: "Iframe", prize: "$1", entry_url: `${SITE}/iframe.html`, frames: ["127.0.0.1:8123/inner.html"], ends: far, limit: { type: "once" }, flags: {}, verification: VER },
  { id: "t-badframe", name: "Unrelated frame", prize: "$1", entry_url: `${SITE}/badframe.html`, ends: far, limit: daily, flags: {}, verification: VER },
  { id: "t-redirect", name: "Redirect", prize: "$1", entry_url: `${SITE}/redirect.html`, ends: far, limit: { type: "rolling24" }, flags: {}, verification: VER },
  { id: "t-ajax", name: "AJAX form", prize: "$1", entry_url: `${SITE}/ajax.html`, ends: far, limit: daily, flags: {}, verification: VER },
  { id: "t-contest", name: "Contest boundary", prize: "$1", entry_url: `${SITE}/contest`, match: ["localhost:8123/contest"], ends: far, limit: daily, flags: {}, verification: VER },
  { id: "t-unverified", name: "Unverified", prize: "$1", entry_url: `${SITE}/unverified.html`, ends: far, limit: daily, flags: {},
    verification: { status: "needs_rules_check", checked_at: "2026-11-04", reason: "Only listing sites checked." } },
  { id: "t-21", name: "Twenty-one plus", prize: "$1", entry_url: `${SITE}/form21.html`, ends: far, limit: daily, min_age: 21, flags: {}, verification: VER },
]};
fs.writeFileSync(path.join(EXT, "giveaways.json"), JSON.stringify(testList, null, 2));

const profile = { firstName: "Test", lastName: "User", email: "giveaways@example.com", phone: "9735550142",
  address1: "123 Main St", address2: "", city: "Newark", state: "NJ", zip: "07102", dob: "2006-05-01" }; // age 20

const ctx = await chromium.launchPersistentContext(fs.mkdtempSync("/tmp/gf-profile-"), {
  headless: true, channel: "chromium",
  args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
  viewport: { width: 1200, height: 900 },
});
let [sw] = ctx.serviceWorkers();
if (!sw) sw = await ctx.waitForEvent("serviceworker");
const extId = sw.url().split("/")[2];
await sleep(1200);
await sw.evaluate(async ({ profile }) => {
  await chrome.storage.local.set({ profile, log: {}, sources: {}, hidden: {},
    settings: { listUrl: "", reminderOn: true, reminderTime: "09:00", showBanner: true } });
}, { profile });
{
  const ext = await ctx.newPage();
  await ext.goto(`chrome-extension://${extId}/options.html`);
  const r = await ext.evaluate(() => chrome.runtime.sendMessage({ type: "refreshList" }));
  check("list loads from disk", r.ok && r.count === testList.giveaways.length, JSON.stringify(r));
  await ext.close();
}
for (const p of ctx.pages()) if (p.url().includes("options.html")) await p.close();
const getLog = () => sw.evaluate(() => chrome.storage.local.get("log").then((x) => x.log || {}));

// ---- 1. main form: fills safely, never submits ----
let page = await ctx.newPage();
await page.goto(`${SITE}/form.html`);
await sleep(1500);
const v = (sel) => page.$eval(sel, (e) => e.value);
check("fills name, email, phone, address, DOB", (await v("#fn")) === "Test" && (await v("[name=lastName]")) === "User" &&
  (await v("[name=email]")) === "giveaways@example.com" && (await v("[name=phone]")) === "(973) 555-0142" &&
  (await v("[name=state]")) === "NJ" && (await v("[name=birth_year]")) === "2006");
check("leaves checkboxes, honeypots, password, SSN, friend email, search alone",
  !(await page.$eval("#rules", (e) => e.checked)) && !(await page.$eval("#optin", (e) => e.checked)) &&
  (await v("#hp1")) === "" && (await v("#hp2")) === "" && (await v("#pw")) === "" && (await v("#ssn")) === "" &&
  (await v("#friend")) === "" && (await v("#search")) === "");
check("React-style input registers the change", (await page.textContent("#state-first")) === "state=Test");
check("never submits on its own", !requests().includes("/submitted.html"));

// ---- 2. a real submit is not logged automatically ----
await page.check("#rules");
await page.click("#submit");
await page.waitForURL(/submitted/);
await sleep(800);
check("submitting does not log an entry by itself", !((await getLog())["t-form"] || []).length);

// ---- 3. AJAX form the site rejects: prompt, but nothing logged until you confirm ----
const aj = await ctx.newPage();
await aj.goto(`${SITE}/ajax.html`);
await sleep(1500);
await aj.click("#xsubmit");
await sleep(500);
check("rejected AJAX submit asks instead of logging", /Did your entry go through/.test(await bannerText(aj)) && !((await getLog())["t-ajax"] || []).length);
await bannerClick(aj, "not-yet");
await sleep(300);
check("'Not yet' logs nothing", !((await getLog())["t-ajax"] || []).length);
await aj.click("#nsubmit"); await sleep(300);
check("newsletter form submit: no prompt", !/Did your entry go through/.test(await bannerText(aj)));
await aj.click("#lgsubmit"); await sleep(300);
check("login form submit: no prompt, password untouched", !/Did your entry go through/.test(await bannerText(aj)) && (await aj.$eval("#lgpw", (e) => e.value)) === "");
await aj.click("#xsubmit"); await sleep(300);
await bannerClick(aj, "log"); await sleep(500);
check("explicit confirmation logs exactly one entry", ((await getLog())["t-ajax"] || []).length === 1 && /Logged/.test(await bannerText(aj)));
await bannerClick(aj, "log"); await sleep(400);
check("a second confirm the same day is refused (daily limit)", ((await getLog())["t-ajax"] || []).length === 1);
await aj.reload(); await sleep(1300);
check("reopening an entered daily giveaway fills nothing", (await aj.$eval("#xemail", (e) => e.value)) === "" && /Already entered/.test(await bannerText(aj)));

// ---- 4. frames: listed provider gets filled, unrelated cross-origin frame doesn't ----
const ifr = await ctx.newPage();
await ifr.goto(`${SITE}/iframe.html`);
await sleep(1800);
const inner = ifr.frames().find((f) => f.url().includes("inner.html"));
check("listed embedded frame is filled", (await inner.$eval("#iemail", (e) => e.value)) === "giveaways@example.com");
const bad = await ctx.newPage();
await bad.goto(`${SITE}/badframe.html`);
await sleep(1800);
const adFrame = bad.frames().find((f) => f.url().includes("inner.html"));
check("unrelated cross-origin frame on an entry page gets nothing", (await adFrame.$eval("#iemail", (e) => e.value)) === "" && (await bad.$eval("#topemail", (e) => e.value)) === "giveaways@example.com");

// ---- 5. a tracked tab that navigates away gets nothing ----
const popup = await ctx.newPage();
await popup.goto(`chrome-extension://${extId}/popup.html?page=1`);
await sleep(800);
await popup.evaluate(() => chrome.runtime.sendMessage({ type: "openGiveaways", ids: ["t-redirect"] }));
await sleep(2500);
const land = ctx.pages().find((p) => p.url().includes("landing.html"));
check("tab opened for a giveaway, then redirected elsewhere: not filled", land && (await land.$eval("#lemail2", (e) => e.value)) === "" && !(await land.$("#giveaway-filler-banner")));
const tm = await sw.evaluate(() => chrome.storage.session.get("tabMap").then((x) => x.tabMap || {}));
check("stale tab tracking is cleared on unrelated navigation", !Object.values(tm).includes("t-redirect"), JSON.stringify(tm));

// ---- 6. path boundary: /contest doesn't match /contest-archive ----
const arch = await ctx.newPage();
await arch.goto(`${SITE}/contest-archive.html`);
await sleep(1300);
check("/contest pattern does not match /contest-archive", (await arch.$eval("#aemail", (e) => e.value)) === "" && !(await arch.$("#giveaway-filler-banner")));

// ---- 7. unverified: no fill until you choose Fill anyway ----
const un = await ctx.newPage();
await un.goto(`${SITE}/unverified.html`);
await sleep(1300);
check("unverified giveaway is not filled on its own", (await un.$eval("#uemail", (e) => e.value)) === "" && /Rules not verified/.test(await bannerText(un)));
await bannerClick(un, "fill-anyway");
await sleep(1500);
check("'Fill anyway' fills it", (await un.$eval("#uemail", (e) => e.value)) === "giveaways@example.com");
await un.reload(); await sleep(1300);
check("'Fill anyway' doesn't stick after the page changes", (await un.$eval("#uemail", (e) => e.value)) === "");

// ---- 8. 21+ hidden for an under-21 profile ----
const p21 = await ctx.newPage();
await p21.goto(`${SITE}/form21.html`);
await sleep(1300);
check("21+ giveaway not filled when under 21", (await p21.$eval("#e21", (e) => e.value)) === "" && /under 21/.test(await bannerText(p21)));

// ---- 9. popup: only verified count as ready; unverified listed separately ----
await popup.reload(); await sleep(900);
const summary = await popup.textContent("#summary");
check("popup separates ready from needs-check", /need a rules check/.test(summary) && /1 need a rules check/.test(summary), summary);
check("Open all excludes unverified", !(await popup.$eval("#due", (e) => e.textContent)).includes("Unverified") && (await popup.$eval("#check", (e) => e.textContent)).includes("Unverified"));
await popup.screenshot({ path: "screens/popup.png", fullPage: true });
const badge = await sw.evaluate(() => chrome.action.getBadgeText({}));
const dueReady = (await popup.$$eval("#due .row", (r) => r.length));
check("badge counts only ready giveaways", badge === String(dueReady), `badge=${badge} ready=${dueReady}`);

// ---- 10. once limit after confirming ----
await ifr.evaluate(() => document.getElementById("giveaway-filler-banner").shadowRoot.querySelector('[data-id="log"]').click());
await sleep(500);
await ifr.reload(); await sleep(1800);
const inner2 = ifr.frames().find((f) => f.url().includes("inner.html"));
check("one-entry giveaway: after logging, nothing fills again", (await inner2.$eval("#iemail", (e) => e.value)) === "" && /one entry allowed/.test(await bannerText(ifr)));

check("only the one real submit you clicked reached the server", requests().split("\n").filter((l) => l.includes("submitted")).length === 1);

await ctx.close();
const failed = results.filter((r) => !r.pass);
fs.writeFileSync("TEST_RESULTS.md", `# Giveaway Filler browser test results\n\nRun: ${new Date().toISOString()}\n\n${results.map((r) => `- ${r.pass ? "PASS" : "FAIL"} ${r.name}${r.detail ? ` (${r.detail})` : ""}`).join("\n")}\n\n${results.length - failed.length}/${results.length} passed.\n`);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
