# Giveaway Filler

A Chrome extension that opens your giveaway entry pages, fills in your details, and tracks each giveaway's entry limit. It never clicks submit. You check the form, tick any boxes you want, do any captcha, and submit yourself.

Version 1.1.0 changes:

- Only giveaways whose sponsor rules were verified count as ready, and only those are opened by Open all.
- The others sit under "Needs a rules check" and won't fill until you click Fill anyway on that page.
- Your details only go to the giveaway's listed entry pages and listed embedded frames.
- An entry is logged only when you confirm it went through.

## Install (2 minutes)

1. In Chrome, go to `chrome://extensions` and turn on Developer mode (top right).
2. Click Load unpacked and pick the `extension` folder.
3. The Settings page opens. Enter your details and click Save details.
4. Pin the extension (puzzle icon in the toolbar, then the pin).

Use your personal Chrome profile, not the NJIT one.

## Daily use

Click the icon, then Open next 10 (or Open all). Each ready entry page opens with your details filled in, outlined in green. On each tab:

1. Check the form.
2. Tick the rules box, plus any opt-ins you actually want.
3. Do any captcha.
4. Click submit.

When the site shows its success or thank-you message, click "It went through, log it" in the helper box at the bottom right, or ✓ Entered in the popup. Submitting alone never logs an entry, because sites often reject or block a submit. The badge on the icon shows how many entries are still due. A reminder notification goes out at 9 AM; you can change the time in Settings.

## What it will and won't do

It fills empty, visible fields: name, email, confirm email, phone, address, city, state, ZIP, country, date of birth, and age.

It never:

- clicks or submits anything
- ticks checkboxes or radio buttons
- touches captchas
- fills passwords, SSN or tax ID, card numbers, friend or referral fields, or hidden honeypot fields

It also never overwrites anything you typed.

It only fills a giveaway's listed entry pages, plus any embedded entry frames listed for that giveaway. A tab that redirects somewhere else, or an unrelated frame such as an ad, gets nothing. It won't fill a giveaway you've already entered for the current entry day, so you can't go over a limit by accident. Each giveaway's day boundary follows its rules: Central time for Ramsey, 9 AM ET for HGTV and Food Network, and so on. When the rules didn't say (Valpak), it waits a full 24 hours between entries.

## Updating the list

The built-in list is the 17 giveaways checked on Nov 3, 2026. Ended ones drop off automatically. To get new ones without reinstalling, point Settings, then Giveaway list, at a `giveaways.json` URL.

To serve the list from the Mac mini over Tailscale:

```bash
mkdir -p ~/giveaways && cp giveaways.json ~/giveaways/
python3 -m http.server 8787 --directory ~/giveaways --bind "$(tailscale ip -4)"
```

Then use `http://firsttradingbot:8787/giveaways.json` as the list URL. The extension checks every 6 hours, and keeps the old list if a new one is broken.

## Tests (run from the tests folder)

- `node tests/test_lib.mjs`: 13 checks on entry-limit and day-boundary logic.
- `tests/test_extension.mjs`: loads the real extension in Chromium against local test forms (39 checks). The results are in `tests/TEST_RESULTS.md`.
