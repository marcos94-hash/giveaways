import json, os, re, sys, datetime as dt, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scraper"))
from finder import norm_url  # noqa: E402

def load(name, default):
    try:
        with open(os.path.join(DATA, name)) as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def save(name, data):
    p = os.path.join(DATA, name); tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False); f.write("\n")
    os.replace(tmp, p)

def now_et():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-5)))  # EST; close enough for dates

def parse_iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]
