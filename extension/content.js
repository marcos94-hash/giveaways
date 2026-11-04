// Giveaway Filler content script.
// Fills empty, visible form fields with your saved details, but only on pages and frames
// the background has authorized for a giveaway. It NEVER clicks, submits, ticks checkboxes,
// picks radio buttons, touches captchas, fills passwords, or fills SSN / tax ID / card
// fields, and it never logs an entry unless you confirm it went through.

(() => {
  if (window.__giveawayFillerLoaded) return;
  window.__giveawayFillerLoaded = true;

  const IS_TOP = window.top === window;
  const filled = new WeakSet();   // elements we filled (never refill if you clear them)
  let filledCount = 0;
  let childCount = 0;
  let ctx = null;                  // reply from background
  let banner = null;

  const MONTHS = ["january","february","march","april","may","june","july","august","september","october","november","december"];

  // ---------- helpers ----------
  const norm = (s) => (s || "").toString().toLowerCase().replace(/[_\-\.\[\]]+/g, " ").replace(/\s+/g, " ").trim();
  const digits = (s) => (s || "").replace(/\D/g, "");
  const pad2 = (n) => String(n).padStart(2, "0");

  function labelText(el) {
    const parts = [];
    if (el.id) {
      try {
        document.querySelectorAll(`label[for="${CSS.escape(el.id)}"]`).forEach((l) => parts.push(l.innerText));
      } catch {}
    }
    const wrap = el.closest("label");
    if (wrap) parts.push(wrap.innerText);
    const lb = el.getAttribute("aria-labelledby");
    if (lb) lb.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) parts.push(n.innerText); });
    // Nearby text for frameworks that put the label in a sibling element.
    // Only trust it when it clearly belongs to this field, not a neighbor.
    if (!parts.length) {
      const prev = el.previousElementSibling;
      const prevIsOthersLabel = prev && prev.tagName === "LABEL" && prev.htmlFor && prev.htmlFor !== el.id;
      if (prev && !prevIsOthersLabel && !prev.querySelector("input,select,textarea") &&
          !/^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(prev.tagName) && prev.innerText && prev.innerText.length < 60) {
        parts.push(prev.innerText);
      }
      const parent = el.parentElement;
      if (parent && !parts.length && parent.querySelectorAll("input,select,textarea").length === 1) {
        const lab = parent.querySelector("label, .label, [class*='label']");
        if (lab && lab !== el && lab.innerText && lab.innerText.length < 60) parts.push(lab.innerText);
      }
    }
    return parts.join(" ");
  }

  function descriptor(el) {
    return norm([
      el.getAttribute("name"), el.id, el.getAttribute("placeholder"),
      el.getAttribute("aria-label"), el.getAttribute("data-testid"),
      el.getAttribute("data-name"), el.getAttribute("title"), labelText(el),
    ].filter(Boolean).join(" | "));
  }

  function isVisible(el) {
    if (el.closest("[aria-hidden='true'], [hidden]")) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    if (r.right < 0 || r.bottom < 0) return false; // pushed off-screen (honeypot trick)
    let n = el;
    while (n && n.nodeType === 1) {
      const cs = getComputedStyle(n);
      if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) < 0.05) return false;
      if (cs.clipPath && cs.clipPath.includes("inset(50%")) return false;
      n = n.parentElement;
    }
    return true;
  }

  // Fields we must never fill.
  const NEVER = /pass ?word|passwd|captcha|recaptcha|\botp\b|one time code|verification code|security code|cvv|cvc|card ?number|credit ?card|ssn|social security|tax ?id|\btin\b|\bein\b|search|query|coupon|promo|referr|friend|recipient|gift message|comment|company|organi[sz]ation|employer|school|user ?name|screen ?name|nick ?name|handle|honey|hpot|\bhp\b|trap|leave (this )?(field )?blank|do not (fill|enter)|bot (check|field)|website|\burl\b|fax/;

  // Decide what a field is. Returns a profile key or null.
  function classify(el) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute("type") || (tag === "select" ? "select" : tag === "textarea" ? "textarea" : "text")).toLowerCase();
    if (["hidden","password","checkbox","radio","submit","button","image","file","reset","range","color","search"].includes(type)) return null;
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
    const d = descriptor(el);
    if (NEVER.test(d)) return null;

    const acMap = {
      "given-name": "firstName", "family-name": "lastName", "name": "fullName",
      "email": "email", "tel": "phone", "tel-national": "phone",
      "address-line1": "address1", "street-address": "address1", "address-line2": "address2",
      "address-level2": "city", "address-level1": "state", "postal-code": "zip",
      "bday": "dob", "bday-day": "dobDay", "bday-month": "dobMonth", "bday-year": "dobYear",
      "country": "country", "country-name": "country",
    };
    for (const tok of ac.split(/\s+/)) if (acMap[tok]) {
      if (acMap[tok] === "email" && /confirm|verify|re ?enter|retype|repeat|again/.test(d)) return "emailConfirm";
      return acMap[tok];
    }

    const dobish = /birth|dob|bday|birthday/.test(d);
    if (type === "date") return dobish ? "dob" : null;
    if (type === "email" || /e ?mail/.test(d)) {
      return /confirm|verify|re ?enter|retype|repeat|again/.test(d) ? "emailConfirm" : "email";
    }
    if (type === "tel" || /phone|mobile|cell|telephone|\btel\b/.test(d)) return "phone";

    if (tag === "select") return classifySelect(el, d, dobish);

    if (dobish) {
      if (/month|\bmm\b/.test(d)) return "dobMonth";
      if (/\bday\b|\bdd\b/.test(d)) return "dobDay";
      if (/year|yyyy|\byy\b/.test(d)) return "dobYear";
      return "dob";
    }
    if (/first ?name|fname|given|forename|\bfirst\b/.test(d)) return "firstName";
    if (/last ?name|lname|surname|family|\blast\b/.test(d)) return "lastName";
    if (/full ?name|your name|^name$|^name \||\| name$|\bname\b/.test(d)) return "fullName";
    if (/address ?(line)? ?2|addr2|\bapt\b|apartment|suite|\bunit\b/.test(d)) return "address2";
    if (/address|street|addr\b|addr1/.test(d) && !/ip address/.test(d)) return "address1";
    if (tag === "textarea") return null;
    if (/\bcity\b|\btown\b/.test(d)) return "city";
    if (/\bstate\b|province|region/.test(d) && !/statement/.test(d)) return "state";
    if (/\bzip\b|postal|post ?code|zipcode/.test(d)) return "zip";
    if (/country/.test(d)) return "country";
    if (/\bage\b/.test(d)) return "age";
    return null;
  }

  function classifySelect(el, d, dobish) {
    const opts = [...el.options].map((o) => norm(o.text + " " + o.value));
    const hasMonths = opts.filter((o) => MONTHS.some((m) => o.includes(m.slice(0, 3)))).length >= 10;
    const years = [...el.options].filter((o) => /^(19|20)\d\d$/.test(o.value.trim() || o.text.trim())).length;
    const days = [...el.options].filter((o) => /^(0?[1-9]|[12]\d|3[01])$/.test((o.value || o.text).trim())).length;
    if (/\bstate\b|province|region/.test(d) || opts.some((o) => o.includes("new jersey"))) {
      if (!/country/.test(d)) return "state";
    }
    if (/country/.test(d)) return "country";
    if (hasMonths && (dobish || /month/.test(d))) return "dobMonth";
    if (years >= 20 && (dobish || /year/.test(d))) return "dobYear";
    if (days >= 28 && (dobish || /\bday\b/.test(d))) return "dobDay";
    // Birthday selects with no label: three selects in a row (month/day/year)
    if (hasMonths) return "dobMonth";
    if (years >= 40) return "dobYear";
    if (days >= 28 && el.options.length <= 33 && el.parentElement) {
      const sibs = [...el.parentElement.parentElement?.querySelectorAll("select") || []].filter((s) => s !== el);
      const monthNear = sibs.some((s) => [...s.options].filter((o) => MONTHS.some((m) => norm(o.text).includes(m.slice(0, 3)))).length >= 10);
      if (monthNear) return "dobDay";
    }
    return null;
  }

  // ---------- values ----------
  function dobParts(p) {
    if (!p.dob) return null;
    const [y, m, d] = p.dob.split("-").map(Number);
    if (!y || !m || !d) return null;
    return { y, m, d };
  }

  function age(p) {
    const b = dobParts(p);
    if (!b) return null;
    const now = new Date();
    let a = now.getFullYear() - b.y;
    if (now.getMonth() + 1 < b.m || (now.getMonth() + 1 === b.m && now.getDate() < b.d)) a--;
    return a;
  }

  function textValue(key, el, p) {
    const ph = (el.getAttribute("placeholder") || "").toLowerCase();
    const max = parseInt(el.getAttribute("maxlength") || "0", 10);
    const b = dobParts(p);
    switch (key) {
      case "firstName": return p.firstName;
      case "lastName": return p.lastName;
      case "fullName": return [p.firstName, p.lastName].filter(Boolean).join(" ");
      case "email": case "emailConfirm": return p.email;
      case "phone": {
        if (max && max < 10) return ""; // split phone boxes: leave for you
        const n = digits(p.phone).replace(/^1(?=\d{10}$)/, "");
        if (n.length !== 10) return p.phone;
        if (ph.includes("(") || max === 14) return `(${n.slice(0,3)}) ${n.slice(3,6)}-${n.slice(6)}`;
        if (/\d{3}-\d{3}-\d{4}|xxx-xxx/.test(ph) || max === 12) return `${n.slice(0,3)}-${n.slice(3,6)}-${n.slice(6)}`;
        return n;
      }
      case "address1": return p.address1;
      case "address2": return p.address2;
      case "city": return p.city;
      case "state": return (p.state || "NJ").toUpperCase();
      case "zip": return (p.zip || "").slice(0, max && max < 5 ? max : 10);
      case "country": return "United States";
      case "age": { const a = age(p); return a ? String(a) : ""; }
      case "dob": {
        if (!b) return "";
        if (el.type === "date") return `${b.y}-${pad2(b.m)}-${pad2(b.d)}`;
        if (/yyyy-mm-dd/.test(ph)) return `${b.y}-${pad2(b.m)}-${pad2(b.d)}`;
        if (/dd\/mm/.test(ph)) return `${pad2(b.d)}/${pad2(b.m)}/${b.y}`;
        if (/mm-dd-yyyy/.test(ph)) return `${pad2(b.m)}-${pad2(b.d)}-${b.y}`;
        return `${pad2(b.m)}/${pad2(b.d)}/${b.y}`;
      }
      case "dobMonth": return b ? (max === 1 ? String(b.m) : pad2(b.m)) : "";
      case "dobDay": return b ? pad2(b.d) : "";
      case "dobYear": return b ? (max === 2 ? String(b.y).slice(2) : String(b.y)) : "";
    }
    return "";
  }

  function selectCandidates(key, p) {
    const b = dobParts(p);
    switch (key) {
      case "state": return [(p.state || "NJ").toLowerCase(), STATE_NAMES[(p.state || "NJ").toUpperCase()] || "new jersey"];
      case "country": return ["us", "usa", "united states", "united states of america", "u s", "u s a"];
      case "dobMonth": return b ? [String(b.m), pad2(b.m), MONTHS[b.m - 1], MONTHS[b.m - 1].slice(0, 3)] : [];
      case "dobDay": return b ? [String(b.d), pad2(b.d)] : [];
      case "dobYear": return b ? [String(b.y)] : [];
    }
    return [];
  }

  const STATE_NAMES = { NJ: "new jersey", NY: "new york", PA: "pennsylvania", CT: "connecticut", DE: "delaware", MD: "maryland", MA: "massachusetts" };

  // React/Vue/Angular-safe value setters.
  function setNative(el, value) {
    const proto = el.tagName === "SELECT" ? HTMLSelectElement.prototype
      : el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new FocusEvent("blur"));
    el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
  }

  function fillSelect(el, key, p) {
    const cands = selectCandidates(key, p).map(norm);
    if (!cands.length) return false;
    const opt = [...el.options].find((o) => cands.includes(norm(o.value)) || cands.includes(norm(o.text)));
    if (!opt || opt.disabled) return false;
    setNative(el, opt.value);
    return true;
  }

  function mark(el) {
    el.style.outline = "2px solid #16a34a";
    el.style.outlineOffset = "1px";
  }

  function fieldsIn(root) {
    return [...root.querySelectorAll("input, select, textarea")];
  }

  function fillAll() {
    if (!ctx || !ctx.fill) return 0;
    const p = ctx.profile;
    let n = 0;
    for (const el of fieldsIn(document)) {
      if (filled.has(el) || el.disabled || el.readOnly) continue;
      if (el.tagName === "SELECT" ? el.selectedIndex > 0 && el.value : el.value) continue; // never overwrite
      if (!isVisible(el)) continue;
      const key = classify(el);
      if (!key) continue;
      let ok = false;
      if (el.tagName === "SELECT") ok = fillSelect(el, key, p);
      else {
        const v = textValue(key, el, p);
        if (v) { setNative(el, v); ok = true; }
      }
      if (ok) { filled.add(el); mark(el); n++; }
    }
    if (n) {
      filledCount += n;
      if (IS_TOP) showState();
      else chrome.runtime.sendMessage({ type: "frameFilled", count: filledCount }).catch(() => {});
    }
    return n;
  }

  // ---------- watching for forms that load late ----------
  let timer = null;
  let watching = false;
  const STOP_AT = Date.now() + 15 * 60 * 1000;
  function schedule() {
    if (Date.now() > STOP_AT || !ctx || !ctx.fill) return;
    clearTimeout(timer);
    timer = setTimeout(fillAll, 500);
  }
  function startWatching() {
    if (watching) return;
    watching = true;
    new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["style", "class", "hidden"] });
    document.addEventListener("click", () => setTimeout(schedule, 300), true);
  }

  // ---------- submissions are never logged automatically ----------
  // Clicking submit is only an attempt: the site may reject it, show an error, or block it
  // in script. So after you submit a form we filled, we just ask whether it went through.
  let submitHooked = false;
  function onSubmit(e) {
    if (!e.isTrusted) return;
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    const ours = fieldsIn(form).filter((el) => filled.has(el)).length;
    if (ours < 2) return; // newsletter boxes, logins and other forms we didn't fill
    if (IS_TOP) askConfirm();
    else chrome.runtime.sendMessage({ type: "frameSubmitAttempt" }).catch(() => {});
  }

  // ---------- on-page helper banner (top frame only) ----------
  function ensureBanner() {
    if (banner) return banner;
    const host = document.createElement("div");
    host.id = "giveaway-filler-banner";
    host.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        .b{font:13px/1.4 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:#0f172a;color:#f8fafc;
           border-radius:10px;padding:12px 14px;width:310px;box-shadow:0 8px 24px rgba(0,0,0,.35)}
        .t{font-weight:600;margin-bottom:4px}
        .m{color:#cbd5e1}
        .w{color:#fdba74}
        .row{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
        button{font:inherit;border:0;border-radius:6px;padding:6px 10px;cursor:pointer}
        .ok{background:#16a34a;color:#fff}
        .warn{background:#b45309;color:#fff}
        .x{background:#334155;color:#e2e8f0}
      </style>
      <div class="b"><div class="t"></div><div class="m"></div><div class="row"></div></div>`;
    document.documentElement.appendChild(host);
    banner = root;
    return banner;
  }

  // buttons: [{ label, cls, id, onClick }]
  function show(html, buttons = []) {
    if (!IS_TOP || !ctx || ctx.showBanner === false) return;
    const b = ensureBanner();
    b.querySelector(".t").textContent = `Giveaway Filler · ${ctx.giveaway.name}`;
    b.querySelector(".m").innerHTML = html;
    const row = b.querySelector(".row");
    row.innerHTML = "";
    for (const btn of [...buttons, { label: "Hide", cls: "x", id: "hide", onClick: () => b.host.remove() }]) {
      const el = document.createElement("button");
      el.className = btn.cls; el.textContent = btn.label; el.dataset.id = btn.id;
      el.addEventListener("click", btn.onClick);
      row.appendChild(el);
    }
  }

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const logButton = { label: "It went through, log it", cls: "ok", id: "log", onClick: logEntry };

  function showState() {
    if (!ctx) return;
    const total = filledCount + childCount;
    if (ctx.ineligible) {
      return show(`<span class="w">This one is ${ctx.minAge}+ and your birth date says you're under ${ctx.minAge}, so nothing was filled. Entering would void the entry.</span>`);
    }
    if (ctx.status && ctx.status.state === "done") {
      return show(`<span class="w">Already entered ${ctx.status.permanent ? "(one entry allowed)" : "for this entry day"}. Entering again would go over the limit, so nothing was filled.</span>`);
    }
    if (ctx.needsProfile) return show(`<span class="w">Add your details in the extension's Settings first.</span>`);
    if (ctx.needsCheck) {
      return show(`<span class="w">Rules not verified yet.</span> ${esc(ctx.reason)} Read the official rules before you enter. Nothing was filled.`,
        [{ label: "Fill anyway", cls: "warn", id: "fill-anyway", onClick: fillAnyway }]);
    }
    const warn = ctx.ready ? "" : `<span class="w">Rules not verified.</span> `;
    show(warn + (total
      ? `Filled ${total} field${total > 1 ? "s" : ""} (green). Check them, tick only the boxes you want, do any captcha, then click submit yourself.`
      : "Waiting for the entry form. If it's behind a button like Enter Now, click it and I'll fill the form."), [logButton]);
  }

  function askConfirm() {
    show("Did your entry go through? Only log it if the page showed a success or thank-you message. If it showed an error, fix it and submit again.",
      [logButton, { label: "Not yet", cls: "x", id: "not-yet", onClick: showState }]);
  }

  async function logEntry() {
    const r = await chrome.runtime.sendMessage({ type: "markEntered", source: "confirmed" }).catch(() => null);
    if (r && r.ok) show("Logged. Nice.");
    else if (r && r.already) show(`<span class="w">Already logged for this entry day.</span>`);
    else show(`<span class="w">Couldn't log it. Tick it in the extension popup instead.</span>`);
  }

  async function fillAnyway() {
    await chrome.runtime.sendMessage({ type: "fillAnyway" }).catch(() => {});
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "childFilled" && IS_TOP) { childCount = Math.max(childCount, msg.count || 0); showState(); }
    if (msg.type === "submitAttempt" && IS_TOP) askConfirm();
    if (msg.type === "refill") start();
  });

  // ---------- start ----------
  async function start() {
    let reply;
    try { reply = await chrome.runtime.sendMessage({ type: "shouldFill" }); } catch { return; }
    if (!reply || !reply.giveaway) return; // not an authorized page or frame: do nothing
    ctx = reply;
    if (IS_TOP) showState();
    if (ctx.fill) { fillAll(); startWatching(); }
    if (!submitHooked) { document.addEventListener("submit", onSubmit, true); submitHooked = true; }
  }
  start();
})();
