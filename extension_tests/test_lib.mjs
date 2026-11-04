// Unit tests for entry-limit logic. Run: node tests/test_lib.mjs
import assert from "node:assert/strict";
import { periodKey, giveawayStatus, matchGiveaway, validateList } from "../extension/lib.js";
import fs from "node:fs";

let n = 0;
const t = (name, fn) => { fn(); n++; console.log("ok -", name); };
const at = (iso) => Date.parse(iso);

const daily = (tz, hour, extra = {}) => ({ id: "x", name: "x", entry_url: "https://a.com/x", ends: "2027-12-31T23:59:00-05:00", limit: { type: "daily", count: 1, reset_tz: tz, reset_hour: hour, ...extra } });

t("ET day boundary at midnight", () => {
  assert.equal(periodKey(at("2026-11-04T23:59:00-05:00"), "America/New_York", 0).key, "2026-11-04");
  assert.equal(periodKey(at("2026-11-05T00:00:30-05:00"), "America/New_York", 0).key, "2026-11-05");
});

t("CT day: 12:30 AM ET is still the previous CT day", () => {
  assert.equal(periodKey(at("2026-11-05T00:30:00-05:00"), "America/Chicago", 0).key, "2026-11-04");
});

t("HGTV 9 AM ET day: 8:59 AM belongs to the previous day", () => {
  assert.equal(periodKey(at("2026-11-05T08:59:00-05:00"), "America/New_York", 9).key, "2026-11-04");
  assert.equal(periodKey(at("2026-11-05T09:00:00-05:00"), "America/New_York", 9).key, "2026-11-05");
});

t("daily: entered today -> done, tomorrow -> due", () => {
  const g = daily("America/New_York", 0);
  const e = [at("2026-11-04T10:00:00-05:00")];
  assert.equal(giveawayStatus(g, e, at("2026-11-04T22:00:00-05:00")).state, "done");
  assert.equal(giveawayStatus(g, e, at("2026-11-05T00:01:00-05:00")).state, "due");
});

t("daily CT: entry at 11:30 PM ET then 12:30 AM ET is the SAME CT day (blocked)", () => {
  const g = daily("America/Chicago", 0);
  const e = [at("2026-11-04T23:30:00-05:00")]; // 10:30 PM CT Nov 4
  const st = giveawayStatus(g, e, at("2026-11-05T00:30:00-05:00")); // 11:30 PM CT Nov 4
  assert.equal(st.state, "done");
  assert.equal(new Date(st.nextAt).toISOString(), "2026-11-05T06:00:00.000Z"); // 1:00 AM ET = midnight CT
});

t("daily with count 2 allows two per day", () => {
  const g = daily("America/New_York", 0); g.limit.count = 2;
  const e = [at("2026-11-04T10:00:00-05:00")];
  assert.equal(giveawayStatus(g, e, at("2026-11-04T11:00:00-05:00")).state, "due");
  e.push(at("2026-11-04T11:00:00-05:00"));
  assert.equal(giveawayStatus(g, e, at("2026-11-04T12:00:00-05:00")).state, "done");
});

t("rolling24 waits 24h + buffer", () => {
  const g = { ...daily("America/New_York", 0), limit: { type: "rolling24" } };
  const e = [at("2026-11-04T20:00:00-05:00")];
  assert.equal(giveawayStatus(g, e, at("2026-11-05T19:59:00-05:00")).state, "done");
  assert.equal(giveawayStatus(g, e, at("2026-11-05T20:04:00-05:00")).state, "done");
  assert.equal(giveawayStatus(g, e, at("2026-11-05T20:06:00-05:00")).state, "due");
});

t("once: done forever after one entry", () => {
  const g = { ...daily("America/New_York", 0), limit: { type: "once" } };
  assert.equal(giveawayStatus(g, [], at("2026-11-04T10:00:00-05:00")).state, "due");
  assert.equal(giveawayStatus(g, [at("2026-11-04T10:00:00-05:00")], at("2026-12-04T10:00:00-05:00")).state, "done");
});

t("ended and not started", () => {
  const g = { ...daily("America/New_York", 0), starts: "2026-11-04T13:00:00-05:00", ends: "2026-11-14T12:00:00-05:00" };
  assert.equal(giveawayStatus(g, [], at("2026-11-04T12:00:00-05:00")).state, "not_started");
  assert.equal(giveawayStatus(g, [], at("2026-11-14T12:00:01-05:00")).state, "ended");
});

t("weekdays only, 1 PM ET reset (IGN)", () => {
  const g = daily("America/New_York", 13, { weekdays_only: true });
  // Sat Nov 7 3 PM ET -> weekend period -> waiting until Mon 1 PM
  const st = giveawayStatus(g, [], at("2026-11-07T15:00:00-05:00"));
  assert.equal(st.state, "waiting");
  assert.equal(new Date(st.nextAt).toISOString(), "2026-11-09T18:00:00.000Z");
  // Mon 11 AM ET is still Sunday's period -> waiting
  assert.equal(giveawayStatus(g, [], at("2026-11-09T11:00:00-05:00")).state, "waiting");
  // Mon 2 PM -> due
  assert.equal(giveawayStatus(g, [], at("2026-11-09T14:00:00-05:00")).state, "due");
  // Fri 2 PM (Friday giveaway) -> due
  assert.equal(giveawayStatus(g, [], at("2026-11-06T14:00:00-05:00")).state, "due");
});

t("URL matching picks the most specific giveaway", () => {
  const list = JSON.parse(fs.readFileSync(new URL("../extension/giveaways.json", import.meta.url))).giveaways;
  assert.equal(matchGiveaway("https://www.ign.com/rewards/win-a-dualsense-ps5-wireless-controller", list).id, "ign-bestbuy-7-dualsense");
  assert.equal(matchGiveaway("https://www.ign.com/rewards/win-something-else", list).id, "ign-bestbuy-daily");
  assert.equal(matchGiveaway("https://www.hgtv.com/sweepstakes/home-for-the-holidays?x=1", list).id, "hgtv-home-for-holidays");
  assert.equal(matchGiveaway("https://daveramsey.com/giveaway", list).id, "ramsey-cash");
  assert.equal(matchGiveaway("https://www.google.com/", list), null);
  assert.equal(matchGiveaway("https://www.hgtv.com/", list), null);
});

t("bundled list validates and every giveaway is open to entry right now or later", () => {
  const data = JSON.parse(fs.readFileSync(new URL("../extension/giveaways.json", import.meta.url)));
  assert.equal(validateList(data), null);
  const now = at("2026-11-03T20:30:00-05:00");
  for (const g of data.giveaways) assert.notEqual(giveawayStatus(g, [], now).state, "ended", g.id);
});

t("validateList rejects junk", () => {
  assert.ok(validateList({}));
  assert.ok(validateList({ giveaways: [{ id: "a", name: "a", entry_url: "javascript:alert(1)", ends: "2027-01-01", limit: { type: "daily" } }] }));
});

console.log(`\n${n} tests passed`);

import { ageFromDob, isEligible, visibleGiveaways } from "../extension/lib.js";
t("age and eligibility", () => {
  const now = Date.parse("2026-11-03T20:00:00-05:00");
  assert.equal(ageFromDob("2006-11-04", now), 19);
  assert.equal(ageFromDob("2006-11-03", now), 20);
  assert.equal(isEligible({ min_age: 21 }, { dob: "2006-01-01" }, now), false);
  assert.equal(isEligible({ min_age: 21 }, { dob: "2004-01-01" }, now), true);
  assert.equal(isEligible({ flags: { age21: true } }, { dob: "2006-01-01" }, now), false);
  assert.equal(isEligible({ min_age: 21 }, {}, now), true); // unknown age: show it
  const list = { giveaways: [{ id: "a", min_age: 18 }, { id: "b", min_age: 21 }, { id: "c", min_age: 18 }] };
  assert.deepEqual(visibleGiveaways(list, { dob: "2006-01-01" }, { c: 1 }, now).map((g) => g.id), ["a"]);
});
console.log("eligibility tests passed");
t("weekly giveaways via rolling hours", () => {
  const g = { id: "w", name: "w", entry_url: "https://a.com", ends: "2027-12-31T00:00:00-05:00", limit: { type: "rolling", hours: 168 } };
  const e = [Date.parse("2026-11-01T10:00:00-05:00")];
  assert.equal(giveawayStatus(g, e, Date.parse("2026-11-07T10:00:00-05:00")).state, "done");
  assert.equal(giveawayStatus(g, e, Date.parse("2026-11-08T10:06:00-05:00")).state, "due");
  assert.equal(validateList({ giveaways: [g] }), null);
});
console.log("rolling tests passed");

import { patternMatches, normUrl as nu, urlMatches, frameAllowed, isReady, schemeAllowed } from "../extension/lib.js";
t("URL patterns need a path boundary unless they end in *", () => {
  assert.equal(patternMatches(nu("https://a.com/contest"), "a.com/contest"), true);
  assert.equal(patternMatches(nu("https://a.com/contest/enter?x=1"), "a.com/contest"), true);
  assert.equal(patternMatches(nu("https://a.com/contest-archive"), "a.com/contest"), false);
  assert.equal(patternMatches(nu("https://a.com/contestant-profile"), "a.com/contest"), false);
  assert.equal(patternMatches(nu("https://a.com/contest-archive"), "a.com/contest*"), true);
  assert.equal(patternMatches(nu("https://evil-a.com/contest"), "a.com/contest"), false);
});
t("entry pages and frames are explicit, https only", () => {
  const g = { entry_url: "https://www.hgtv.com/sweepstakes/x", match: ["hgtv.com/sweepstakes/x"], frames: ["xd.wayin.com"] };
  assert.equal(urlMatches(g, "https://hgtv.com/sweepstakes/x"), true);
  assert.equal(urlMatches(g, "http://hgtv.com/sweepstakes/x"), false);
  assert.equal(urlMatches(g, "https://hgtv.com/sweepstakes/other"), false);
  assert.equal(frameAllowed(g, "https://xd.wayin.com/display/container/1"), true);
  assert.equal(frameAllowed(g, "https://ads.example.net/frame"), false);
  assert.equal(urlMatches(g, "https://xd.wayin.com/display/container/1"), false); // a frame host is not an entry page
  assert.equal(schemeAllowed("http://localhost:8123/x"), true);
  assert.equal(schemeAllowed("http://example.com/x"), false);
});
t("only sponsor-verified listings are ready", () => {
  assert.equal(isReady({ verification: { status: "verified" } }), true);
  assert.equal(isReady({ verification: { status: "needs_rules_check" } }), false);
  assert.equal(isReady({ rules_checked: "full" }), false); // old field alone is not enough
});
console.log("pattern/frame/readiness tests passed");
