import datetime as dt, json, os, sys, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scraper"))
import finder

FX = pathlib.Path(__file__).parent / "fixtures"
TODAY = dt.date(2026, 11, 3)

def test_dates():
    assert finder.parse_date_info("Mon, Nov 30", TODAY) == (dt.date(2026, 11, 30), "inferred")
    assert finder.parse_date_info("Jan 6", TODAY) == (dt.date(2027, 1, 6), "inferred")
    assert finder.parse_date_info("January 6, 2027", TODAY) == (dt.date(2027, 1, 6), "explicit")
    assert finder.parse_date("Mon, Nov 30", TODAY) == dt.date(2026, 11, 30)
    assert finder.parse_date("Jan 6", TODAY) == dt.date(2027, 1, 6)
    assert finder.parse_date("January 6, 2027", TODAY) == dt.date(2027, 1, 6)
    assert finder.parse_date("12/15/26", TODAY) == dt.date(2026, 12, 15)
    assert finder.parse_date("2027-01-31", TODAY) == dt.date(2027, 1, 31)
    assert finder.parse_date("Dec. 25th, 2026", TODAY) == dt.date(2026, 12, 25)

def test_extract_fst():
    c = finder.extract("https://www.freestufftimes.com/contests/27/knot/", (FX / "fst_knot.html").read_text(), "freestufftimes.com", TODAY)
    assert c["title"] == "The Knot Get Aisle Ready Sweepstakes", c["title"]
    assert c["entry_url"] == "https://sweepwidget.com/c/103277-vtmslewf"
    assert c["rules_url"] == "https://www.theknot.com/rules"
    assert c["ends_guess"] == "2026-11-30"
    assert c["frequency_guess"] == "daily"
    assert c["min_age_guess"] == 18
    assert c["value_guess"] == 5000
    assert c["category_guess"] in ("cash", "gift_card")
    decision, why = finder.keep(c, TODAY); assert decision == "keep", why

def test_extract_labeled():
    c = finder.extract("https://x.com/p", (FX / "fst_ps5.html").read_text(), "freestufftimes.com", TODAY)
    assert c["entry_url"] == "https://gleam.io/abc/win-a-ps5-pro"
    assert c["frequency_guess"] == "once" and c["min_age_guess"] == 21 and c["ends_guess"] == "2026-12-15"
    assert c["category_guess"] == "electronics"
    assert not c["flags"]["nj_excluded"]

def test_yearless_past_date_is_not_next_year():
    # An archived "October 1" seen on Nov 4 must not become Oct 1 next year.
    assert finder.parse_date_info("October 1", dt.date(2026, 11, 4)) == (None, "uncertain")
    html_ = "<html><body><h1>Old giveaway</h1><p>Ends: October 1</p><a href='https://gleam.io/x/old'>Enter</a></body></html>"
    c = finder.extract("https://www.freestufftimes.com/contests/1/old/", html_, "freestufftimes.com", dt.date(2026, 11, 4))
    assert c["ends_guess"] is None and c["ends_how"] == "uncertain" and "October 1" in c["ends_text"]
    decision, _ = finder.keep(c, dt.date(2026, 11, 4))
    assert decision == "keep" and "end_date_uncertain" in c["review_flags"]

def test_heuristic_flags_go_to_review_not_dropped():
    # Local-only (could be NJ-local), NJ-excluded text, purchase text: kept with flags for review.
    html_ = """<html><body><h1>Local radio giveaway</h1><p>Must live within the station's listening area.
    Void in New Jersey. Purchase required. Ends: December 20, 2026</p>
    <a href="https://station.example.com/contest/enter">Enter here</a></body></html>"""
    c = finder.extract("https://thefreebieguy.com/sweepstakes/local/", html_, "thefreebieguy.com", TODAY)
    decision, why = finder.keep(c, TODAY)
    assert decision == "keep", why
    assert {"local_only", "nj_excluded", "purchase_required"} <= set(c["review_flags"])
    # Established facts still drop: social-media entry link, explicit past end date.
    c2 = finder.extract("https://x.com/p", "<h1>IG</h1><p>Ends: Dec 20, 2026</p><a href='https://www.instagram.com/p/1'>Enter</a>", "freestufftimes.com", TODAY)
    assert finder.keep(c2, TODAY)[0] == "drop"
    c3 = finder.extract("https://x.com/p", "<h1>Old</h1><p>Ends: October 1, 2026</p><a href='https://gleam.io/x/y'>Enter</a>", "freestufftimes.com", TODAY)
    assert finder.keep(c3, TODAY) == ("drop", "ended")

def test_excluded_prize_hint_from_title_only():
    for title, hint in [('Win this $22,000 Noveske 12.5" 6.5 Creedmoor', True), ("Thermal Gear and Hog Hunt Sweepstakes", True),
                        ("Win a Year of Wine", True), ("Win 1 of 6 Gift Cards from Yankee Candle!", False),
                        ("GOWOOD sunglasses Giveaway", False), ("Win an Electric Bike + More", False)]:
        html_ = f"<h1>{title}</h1><p>Ends: December 20, 2026. Beer and wine sidebar ad.</p><a href='https://gleam.io/x/y'>Enter</a>"
        c = finder.extract("https://www.freestufftimes.com/contests/03/x/", html_, "freestufftimes.com", TODAY)
        assert finder.keep(c, TODAY)[0] == "keep"
        assert ("excluded_prize_hint" in c["review_flags"]) == hint, (title, c["review_flags"])

def test_missing_entry_link_is_retried_then_given_up():
    d0 = dt.date(2026, 11, 4)
    e1 = finder.mark_seen(None, d0, "retry")
    assert e1["status"] == "retry" and not finder.due_for_fetch(e1, d0) and finder.due_for_fetch(e1, d0 + dt.timedelta(days=1))
    e2 = finder.mark_seen(e1, d0 + dt.timedelta(days=1), "retry")
    e3 = finder.mark_seen(e2, d0 + dt.timedelta(days=2), "retry")
    assert e3["status"] == "gave_up" and not finder.due_for_fetch(e3, d0 + dt.timedelta(days=10))
    assert finder.mark_seen(e1, d0 + dt.timedelta(days=1), "keep")["status"] == "done"
    assert not finder.due_for_fetch("2026-11-01", d0)  # old seen.json format still means parsed

def test_rules_link_not_entry():
    html_ = """<html><body><h1>Win $400</h1><p>ENDING – November 6, 2026</p>
    <p>OFFICIAL RULES – <a href="https://www.tablotv.com/wp-content/uploads/2026/10/Rules.pdf">Click Here</a></p>
    <p><a href="https://www.tablotv.com/race-weekend">Click here to enter</a></p></body></html>"""
    c = finder.extract("https://thefreebieguy.com/sweepstakes/x/", html_, "thefreebieguy.com", TODAY)
    assert c["entry_url"] == "https://www.tablotv.com/race-weekend", c["entry_url"]
    assert c["rules_url"].endswith("Rules.pdf")

def test_category_ignores_menu_after_head_title():
    # The <title> repeats the post title before the site menu ("Best Cash Back Apps"); the guess must use the post body.
    html_ = """<html><head><title>Win a New Boat in The Bass Sweepstakes! - The Freebie Guy</title></head>
    <body><nav><a href="/">Home</a><a href="/c">Best Cash Back Apps</a><a href="/g">Gift Card Deals</a></nav>
    <article><h1>Win a New Boat in The Bass Sweepstakes!</h1><p>One winner gets a bass boat. Ends: December 20, 2026</p>
    <a href="https://gleam.io/x/bass">Enter here</a></article></body></html>"""
    c = finder.extract("https://thefreebieguy.com/sweepstakes/bass/", html_, "thefreebieguy.com", TODAY)
    assert c["title"] == "Win a New Boat in The Bass Sweepstakes!", c["title"]
    assert c["category_guess"] == "other", c["category_guess"]
    assert c["entry_url"] == "https://gleam.io/x/bass"

def test_filters():
    c = finder.extract("https://x.com/c", (FX / "fst_canada.html").read_text(), "freestufftimes.com", TODAY)
    assert finder.keep(c, TODAY)[0] == "keep" and "foreign_only" in c["review_flags"]
    t = "Open to US residents. Void in Florida, New Jersey and Rhode Island."
    assert finder.flags_for(t, "https://a.com")["nj_excluded"]
    assert not finder.flags_for("No purchase necessary. A purchase will not increase your odds.", "https://a.com")["purchase_required"]
    assert finder.flags_for("Purchase required. Upload your receipt.", "https://a.com")["purchase_required"]
    assert finder.flags_for("x", "https://www.instagram.com/p/1")["social_entry"]

def test_main_offline(monkeypatch=None):
    pages = {
        "https://www.freestufftimes.com/contests/": "fst_list.html",
        "https://www.freestufftimes.com/contests/27/the-knot-get-aisle-ready-sweepstakes/": "fst_knot.html",
        "https://www.freestufftimes.com/contests/03/win-a-ps5-pro/": "fst_ps5.html",
        "https://www.freestufftimes.com/contests/03/canada-only-cash/": "fst_canada.html",
    }
    def fake_fetch(u):
        if u not in pages: raise OSError("404 " + u)
        return u, (FX / pages[u]).read_text()
    finder.fetch = fake_fetch
    finder.allowed = lambda u: True
    real_today = finder.dt.date
    class FakeDate(dt.date):
        @classmethod
        def today(cls): return TODAY
    finder.dt.date = FakeDate
    try:
        d = tempfile.mkdtemp()
        sys.argv = ["finder", "--out", f"{d}/c.json", "--report", f"{d}/r.json", "--state", f"{d}/seen.json", "--only", "freestufftimes"]
        finder.main()
        out = json.load(open(f"{d}/c.json")); rep = json.load(open(f"{d}/r.json"))
        assert out["count"] == 3, out["count"]
        canada = [c for c in out["candidates"].values() if "canada" in c["title"].lower()][0]
        assert "foreign_only" in canada["review_flags"]
        s = rep["sources"]["freestufftimes"]
        assert s["detail_links"] == 3 and s["parsed"] == 3 and s["kept"] == 3, s
        assert s["dropped"] == {}, s["dropped"]   # "Canadian residents only" is a heuristic: kept, flagged
        # second run: details already seen are not refetched, candidates kept
        finder.main()
        out2 = json.load(open(f"{d}/c.json")); rep2 = json.load(open(f"{d}/r.json"))
        assert out2["count"] == 3 and rep2["sources"]["freestufftimes"]["parsed"] == 0
    finally:
        finder.dt.date = real_today

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"): f(); print("ok -", n)
