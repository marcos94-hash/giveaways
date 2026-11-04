"""Review queue regressions: statuses, retries, starvation, interrupted runs, verification rules.
Run: python3 tests/test_review.py
"""
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import reviewlib as R  # noqa: E402

T0 = R.parse("2026-11-04T09:00:00-05:00")


def cand(i, **kw):
    return {"title": f"Giveaway {i}", "entry_url": f"https://gleam.io/x/{i}", "ends_guess": "2026-12-31",
            "category_guess": "other", "frequency_guess": "daily", **kw}


def setup(n_new=10):
    cands = {f"https://gleam.io/x/{i}": cand(i) for i in range(n_new)}
    return {"version": 2, "items": {}}, {"giveaways": []}, cands


def listing(**kw):
    g = {"id": "x", "name": "X", "prize": "$100", "entry_url": "https://example.com/enter",
         "ends": "2026-12-31T23:59:00-05:00", "limit": {"type": "once"},
         "verification": {"status": "verified", "rules_source": "https://example.com/rules", "checked_at": "2026-11-04T08:00:00-05:00",
                          "confirmed": {k: True for k in R.CONFIRM_KEYS}}}
    g.update(kw)
    return g


def test_verified_needs_sponsor_rules_and_all_four_confirmations():
    assert R.validate_listing(listing(), T0) == []
    g = listing(); g["verification"]["confirmed"]["entry_limit"] = False
    assert any("entry_limit" in e for e in R.validate_listing(g, T0))
    g = listing(); g["verification"]["rules_source"] = None
    assert any("rules_source" in e for e in R.validate_listing(g, T0))
    g = listing(verification={"status": "needs_rules_check", "checked_at": "2026-11-04"})
    assert any("reason" in e for e in R.validate_listing(g, T0))
    g = listing(verification={"status": "needs_rules_check", "checked_at": "2026-11-04", "reason": "rules didn't load"})
    assert R.validate_listing(g, T0) == []
    assert any("https" in e for e in R.validate_listing(listing(entry_url="http://example.com/enter"), T0))
    assert any("frames" in e for e in R.validate_listing(listing(frames=["https://xd.wayin.com"]), T0))
    assert any("verification" in e for e in R.validate_listing({k: v for k, v in listing().items() if k != "verification"}, T0))


def test_rejected_is_permanent_and_needs_a_code():
    log, data, cands = setup(3)
    k = "https://gleam.io/x/0"
    try:
        R.record(log, k, "rejected", "", "no code", t=T0)
        raise AssertionError("should need a code")
    except ValueError:
        pass
    R.record(log, k, "rejected", "not_open_to_nj", "excludes NJ", t=T0)
    for days in (1, 5, 30):
        picked, _ = R.plan(log, cands, data, 10, T0 + dt.timedelta(days=days))
        assert k not in picked


def test_blocked_backs_off_then_parks():
    log, data, cands = setup(1)
    k = "https://gleam.io/x/0"
    t = T0
    for expect_days in R.BACKOFF_DAYS:
        it = R.record(log, k, "blocked", "js_only", "page didn't load", t=t)
        assert it["status"] == "blocked"
        assert R.parse(it["next_retry_at"]) == t + dt.timedelta(days=expect_days)
        assert k not in R.plan(log, cands, data, 5, t + dt.timedelta(days=expect_days) - dt.timedelta(minutes=1))[0]
        t = t + dt.timedelta(days=expect_days)
        assert k in R.plan(log, cands, data, 5, t)[0]
    it = R.record(log, k, "blocked", "js_only", "still won't load", t=t)
    assert it["status"] == "parked" and it["next_retry_at"] is None
    assert k not in R.plan(log, cands, data, 5, t + dt.timedelta(days=60))[0]


def test_retries_cannot_starve_new_items_and_vice_versa():
    log, data, cands = setup(30)
    for i in range(20, 30):  # 10 retry-due items
        R.record(log, f"https://gleam.io/x/{i}", "blocked", "js_only", "x", t=T0 - dt.timedelta(days=2))
    picked, info = R.plan(log, cands, data, 10, T0)
    retries = [k for k in picked if k in log["items"]]
    assert info["retry_due"] == 10 and info["new_waiting"] == 20
    assert 1 <= len(retries) <= 3 and len(picked) == 10   # new items get at least 70%
    # with no new items left, retries fill the batch
    for i in range(20):
        R.record(log, f"https://gleam.io/x/{i}", "rejected", "other", "x", t=T0)
    picked, _ = R.plan(log, cands, data, 10, T0)
    assert len(picked) == 10 and all(log["items"][k]["status"] == "blocked" for k in picked)
    # oldest retry goes first (no starvation among retries)
    R.record(log, "https://gleam.io/x/25", "blocked", "js_only", "x", t=T0 - dt.timedelta(days=9))
    assert R.plan(log, cands, data, 1, T0 + dt.timedelta(days=2))[0] == ["https://gleam.io/x/25"]


def test_interrupted_run_resumes_first_and_claims_are_exclusive():
    log, data, cands = setup(10)
    picked, _ = R.plan(log, cands, data, 4, T0)
    R.claim(log, picked, "run-A", T0)
    R.record(log, picked[0], "rejected", "ended", "x", t=T0)  # run A finished one, then died
    # another run while A's claims are live does not take them
    p2, _ = R.plan(log, cands, data, 10, T0 + dt.timedelta(minutes=30))
    assert not set(p2) & set(picked)
    # after the claim expires the leftovers come back, first in line, with no attempt counted
    t = T0 + dt.timedelta(hours=R.CLAIM_HOURS, minutes=1)
    resumed = R.release_expired(log, t)
    assert set(resumed) == set(picked[1:])
    p3, info = R.plan(log, cands, data, 3, t)
    assert set(p3) <= set(resumed) and len(p3) == 3, (p3, resumed)
    assert info["resume"] == 3
    assert all(log["items"].get(k, {}).get("attempts", 0) == 0 for k in resumed)
    # a fresh claim on resumed items, then recording, clears the interrupted marker
    R.claim(log, p3, "run-C", t)
    R.record(log, p3[0], "rejected", "other", "x", t=t)
    assert "interrupted_at" not in log["items"][p3[0]]
    assert log["items"][picked[0]]["status"] == "rejected"


def test_release_run_hands_back_unrecorded_items():
    log, data, cands = setup(5)
    R.record(log, "https://gleam.io/x/0", "needs_review", "incomplete_info", "x", t=T0 - dt.timedelta(days=3))
    picked, _ = R.plan(log, cands, data, 5, T0)
    R.claim(log, picked, "run-B", T0)
    R.record(log, picked[1], "rejected", "other", "x", t=T0)
    back = R.release_run(log, "run-B")
    assert picked[1] not in back and len(back) == 4
    assert log["items"]["https://gleam.io/x/0"]["status"] == "needs_review"
    assert log["items"]["https://gleam.io/x/0"]["attempts"] == 1  # unchanged by the claim
    assert all(k not in log["items"] or log["items"][k]["status"] != "in_progress" for k in picked)


def test_unverified_listings_come_back_for_upgrade():
    log, data, cands = setup(0)
    g = listing(id="u", entry_url="https://example.com/u",
                verification={"status": "needs_rules_check", "checked_at": "2026-11-04", "reason": "rules didn't load"})
    gl, how = R.upsert_listing(data, g, T0)
    R.record(log, "https://example.com/u", "listed", "needs_rules_check", "x", t=T0, listing_id=gl["id"], verified=False)
    assert R.plan(log, cands, data, 5, T0 + dt.timedelta(days=R.RECHECK_UNVERIFIED_DAYS, minutes=1))[0] == ["https://example.com/u"]
    # upgrading keeps id and added date, refreshes verification
    g2 = listing(id="", entry_url="https://example.com/u")
    gl2, how2 = R.upsert_listing(data, g2, T0)
    assert how2 == "updated" and gl2["id"] == "u" and gl2["verification"]["status"] == "verified"


def test_sweep_retires_ended_items():
    log, data, cands = setup(2)
    cands["https://gleam.io/x/0"]["ends_guess"] = "2026-11-03"
    R.record(log, "https://gleam.io/x/0", "blocked", "js_only", "x", t=T0 - dt.timedelta(days=2))
    g, _ = R.upsert_listing(data, listing(id="soon", entry_url="https://example.com/soon", ends="2026-11-05T00:00:00-05:00"), T0)
    R.record(log, "https://example.com/soon", "listed", "verified", "", t=T0, listing_id="soon", verified=True)
    out = R.sweep(log, data, cands, T0 + dt.timedelta(days=1))
    assert out["listings_ended"] == ["X"] and data["giveaways"] == []
    assert log["items"]["https://example.com/soon"]["status"] == "ended"
    assert log["items"]["https://gleam.io/x/0"]["status"] == "ended"


def test_v1_log_migrates():
    import json, os, tempfile
    d = tempfile.mkdtemp()
    old = R.DATA
    R.DATA = d
    try:
        json.dump({"reviewed": {"https://a.com/x": {"verdict": "rejected", "name": "A", "reason": "excludes New Jersey", "date": "2026-11-03"},
                                "https://b.com/y": {"verdict": "accepted", "name": "B", "date": "2026-11-03"}}},
                  open(os.path.join(d, "review_log.json"), "w"))
        log = R.load_log()
        assert log["version"] == 2
        assert log["items"]["https://a.com/x"]["status"] == "rejected" and log["items"]["https://a.com/x"]["reason_code"] == "not_open_to_nj"
        assert log["items"]["https://b.com/y"]["status"] == "listed"
    finally:
        R.DATA = old


if __name__ == "__main__":
    n = 0
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f(); n += 1; print("ok -", name)
    print(f"{n} review tests passed")
