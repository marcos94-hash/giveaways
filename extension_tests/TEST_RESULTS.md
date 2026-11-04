# Giveaway Filler browser test results

Run: 2026-11-04T05:31:21.633Z

- PASS list loads from disk ({"ok":true,"source":"bundled","count":9})
- PASS fills name, email, phone, address, DOB
- PASS leaves checkboxes, honeypots, password, SSN, friend email, search alone
- PASS React-style input registers the change
- PASS never submits on its own
- PASS submitting does not log an entry by itself
- PASS rejected AJAX submit asks instead of logging
- PASS 'Not yet' logs nothing
- PASS newsletter form submit: no prompt
- PASS login form submit: no prompt, password untouched
- PASS explicit confirmation logs exactly one entry
- PASS a second confirm the same day is refused (daily limit)
- PASS reopening an entered daily giveaway fills nothing
- PASS listed embedded frame is filled
- PASS unrelated cross-origin frame on an entry page gets nothing
- PASS tab opened for a giveaway, then redirected elsewhere: not filled
- PASS stale tab tracking is cleared on unrelated navigation ({})
- PASS /contest pattern does not match /contest-archive
- PASS unverified giveaway is not filled on its own
- PASS 'Fill anyway' fills it
- PASS 'Fill anyway' doesn't stick after the page changes
- PASS 21+ giveaway not filled when under 21
- PASS popup separates ready from needs-check (6 ready · 1 done · 1 need a rules check)
- PASS Open all excludes unverified
- PASS badge counts only ready giveaways (badge=6 ready=6)
- PASS one-entry giveaway: after logging, nothing fills again
- PASS only the one real submit you clicked reached the server

27/27 passed.
