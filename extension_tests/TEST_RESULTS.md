# Giveaway Filler browser test results

Run: 2026-11-04T05:38:00.057Z

- PASS list loads from disk ({"ok":true,"source":"bundled","count":12})
- PASS fills name, email, phone, address, DOB
- PASS leaves checkboxes, honeypots, password, SSN, friend email, search alone
- PASS React-style input registers the change
- PASS never submits on its own
- PASS submitting does not log an entry by itself
- PASS rejected AJAX submit asks instead of logging
- PASS 'Not yet' logs nothing
- PASS unconfirmed attempt stays retryable: a re-rendered form is filled again
- PASS newsletter form submit: no prompt
- PASS login form submit: no prompt, password untouched
- PASS explicit confirmation logs exactly one entry
- PASS after confirming, a re-rendered form on the same page is not filled again
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
- PASS not-started giveaway: nothing filled, 'Not open yet' shown (
      
        .b{font:13px/1.4 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:#0f172a;color:#f)
- PASS not-started + unverified: no Fill anyway offered
- PASS Fill anyway request on a not-started page still fills nothing
- PASS waiting (weekday-only on a Saturday): nothing filled, next entry time shown (
      
        .b{font:13px/1.4 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:#0f172a;color:#f8fafc;
           bo)
- PASS same weekday-only giveaway fills on a real entry day (Wed)
- PASS popup separates ready from needs-check (7 ready · 1 done · 1 need a rules check)
- PASS Open all excludes unverified
- PASS badge counts only ready giveaways (badge=7 ready=7)
- PASS after confirming, a re-rendered form inside a frame is not filled again
- PASS one-entry giveaway: after logging, nothing fills again
- PASS only the one real submit you clicked reached the server

35/35 passed.
