# Giveaway Filler (Chrome extension) setup

Giveaway Filler opens giveaway entry pages, fills in your saved details, and tracks each giveaway's entry limit. It never clicks submit. You check the form, tick only the boxes you want, do any captcha, and submit yourself.

These notes match version 1.1.1 (`manifest.json`). The canonical copy is `extension/README.md` in the giveaways repo. The local `Giveaway_Filler/README.md` is the same file.

## Install (unpacked)

1. In your personal Chrome profile (not the NJIT one), go to `chrome://extensions`.
2. Turn on Developer mode (top right).
3. Click Load unpacked and pick the `extension` folder.
4. The Settings page opens on first install. Fill it in (see "Local setup" below) and click Save details.
5. Pin the extension: puzzle icon in the toolbar, then the pin.

Leave Developer mode on. This is an unpacked install, and Chrome disables unpacked extensions when Developer mode is turned off. If that happens, turn Developer mode back on and switch Giveaway Filler back on in `chrome://extensions`.

The extension asks for access to all sites because entry pages are on many different domains. It only fills pages that are listed for a giveaway (see "What it fills").

### Updating the extension code

An unpacked extension doesn't update itself. To update, replace the files in the `extension` folder, then click the reload arrow on Giveaway Filler's card in `chrome://extensions`. Reloading keeps your saved details and entry log. Removing the extension deletes them.

## Local setup (your details stay in this browser)

Open Settings (right-click the icon, then Options). Your details are stored only in this Chrome profile, never in the giveaways repo.

- Required: first name, last name and email. Until these are saved, the popup says "Add your name and email in Settings" and the helper on an entry page says "Add your details in the extension's Settings first", with every field left blank.
- Birth date: save it. It's used for age filtering. With no birth date saved, the extension doesn't know your age, so 21+ giveaways still show, count in the badge and fill. With it saved, giveaways above your age are hidden from the popup (the footer shows "N hidden (age limit)"), and their pages show a warning and fill nothing. It also fills date-of-birth and age fields that some forms ask for.
- Optional: phone, street address, apt or unit, city, state (defaults to NJ) and ZIP. Use your legal name and a mailing address that matches your ID, since sponsors verify winners.
- Daily reminder: on by default at 9:00 AM. It only fires when a verified giveaway is due.
- On-page helper: the small box at the bottom right of entry pages. Keep it on, because it's where you confirm entries.

## Where the list comes from

By default the extension reads the daily-reviewed list from GitHub:

    https://raw.githubusercontent.com/marcos94-hash/giveaways/main/data/giveaways.json

Leave Settings, then Giveaway list, then List URL blank to use it. Put a different https URL there only to use a different list.

When it refreshes:

- when the extension is installed or reloaded
- when Chrome starts
- every 60 minutes while Chrome is running
- each time you open the popup
- when you click Save and refresh in Settings

A downloaded list is checked before it's used. If the download fails or the list is malformed, the extension keeps the previous list and shows "List update failed" in the popup and "Last update failed" in Settings. GitHub's raw file can lag a few minutes behind a push.

The `giveaways.json` inside the `extension` folder is a built-in fallback snapshot. It's only used before the first successful download. The popup footer and Settings say which list is in use, with its source and fetch time. Ended giveaways drop off automatically.

Each listing is either:

- verified: the sponsor's own rules were checked for eligibility, free entry, deadline and entry limit
- needs a rules check

Giveaway rules and extra requirements are in each listing's Details in the popup. Examples are a free account to create yourself, social follows the rules require, or a marketing opt-in. The extension never creates accounts, follows anyone or ticks opt-in boxes.

## Daily use

The popup has four sections: Ready to enter, Needs a rules check, Done for now, and Opens later. The badge counts verified giveaways that are due now.

Open next 10 (or Open all, when 10 or fewer are due) opens only verified giveaways that are due, with your details filled in and outlined in green. On each tab:

1. Check the form.
2. Tick the rules box, plus any opt-ins you actually want.
3. Do any captcha.
4. Click submit yourself.

Needs-a-rules-check giveaways are never opened by that button and don't fill on their own. If you open one, the helper says "Rules not verified yet" and offers Fill anyway. Fill anyway lasts for that one page load only. Read the official rules first.

Nothing fills before a giveaway opens, between its entry days, or after you've already entered for the current entry period. The helper says when the next entry opens. Each giveaway's day boundary follows its rules. When the rules don't define a day, it waits 24 hours between entries.

## Confirm each successful entry

Submitting doesn't log an entry, because sites often reject a submit or show an error.

After you submit a form the extension filled, the helper asks "Did your entry go through?":

- Click "It went through, log it" only after the site shows a success or thank-you message.
- Click "Not yet" if it showed an error. Fix it and submit again.

You can also tick ✓ Entered in the popup after the site confirms. Undo removes the last logged entry. Once an entry is logged, that page won't fill again for the entry period, even if the form re-renders. Skip hides a giveaway, and "show skipped" in the popup footer brings skipped ones back. Settings can export the entry log as CSV or clear it.

## What it fills

It fills empty, visible fields only: name, email, confirm email, phone, address, city, state, ZIP, country, date of birth and age. It never overwrites what you typed.

It never:

- clicks or submits anything
- ticks checkboxes or radio buttons
- touches captchas
- fills passwords, SSN or tax ID, card numbers, friend or referral fields, or hidden honeypot fields

Your details go only to a giveaway's listed entry pages and its listed embedded entry frames. A tab that redirects elsewhere, or an unrelated frame such as an ad, gets nothing.

## Tests

The tests live in `extension_tests/` in the repo and in `tests/` in the local Giveaway_Filler folder. Run them from that folder.

- `node test_lib.mjs`: 18 checks on entry limits, day boundaries, URL and frame matching, and readiness.
- `python3 server.py site /tmp/gf_server.log &` then `node test_extension.mjs`: loads the real extension in Chromium (Playwright) against local test forms. 35 checks; the latest results are in `TEST_RESULTS.md`.
