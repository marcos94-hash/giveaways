import datetime as dt, json, os, sys, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scraper"))
import finder

FX = pathlib.Path(__file__).parent / "fixtures"
TODAY = dt.date(2026, 11, 3)

def test_dates():
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
    ok, why = finder.keep(c, TODAY); assert ok, why

def test_extract_labeled():
    c = finder.extract("https://x.com/p", (FX / "fst_ps5.html").read_text(), "freestufftimes.com", TODAY)
    assert c["entry_url"] == "https://gleam.io/abc/win-a-ps5-pro"
    assert c["frequency_guess"] == "once" and c["min_age_guess"] == 21 and c["ends_guess"] == "2026-12-15"
    assert c["category_guess"] == "electronics"
    assert not c["flags"]["nj_excluded"]

def test_filters():
    c = finder.extract("https://x.com/c", (FX / "fst_canada.html").read_text(), "freestufftimes.com", TODAY)
    assert finder.keep(c, TODAY) == (False, "not open to US")
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
        assert out["count"] == 2, out["count"]
        s = rep["sources"]["freestufftimes"]
        assert s["detail_links"] == 3 and s["parsed"] == 3 and s["kept"] == 2, s
        assert s["dropped"] == {"not open to US": 1}
        # second run: details already seen are not refetched, candidates kept
        finder.main()
        out2 = json.load(open(f"{d}/c.json")); rep2 = json.load(open(f"{d}/r.json"))
        assert out2["count"] == 2 and rep2["sources"]["freestufftimes"]["parsed"] == 0
    finally:
        finder.dt.date = real_today

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"): f(); print("ok -", n)
