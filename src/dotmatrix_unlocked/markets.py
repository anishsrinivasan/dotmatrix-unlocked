"""Markets skin: rows of LABEL  VALUE, green up / red down on the day.

Indian bullion (IBJA), rupee rates (ECB, crossed through USD), Nifty and Brent come from snapdata.dev:
free, no key, daily.
US stocks come from Yahoo's chart endpoint: free, no key, unofficial (ponytail: if Yahoo locks it down,
swap in a keyed provider such as Finnhub here; nothing else changes)."""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from PIL import Image

from . import render

FX = (120, 200, 255)
INR = "USD.INR.RATE"
# id -> (snapdata instruments multiplied together, ^-1 to divide; panel label, label colour)
# ECB quotes everything against USD, so X -> rupee is X/USD x USD/INR (or USD/INR / USD/X).
SNAP = {
    "GOLD": ([("XAU.24K.INR.G", 1)], "AU", (255, 190, 40)),
    "GOLD22": ([("XAU.22K.INR.G", 1)], "22K", (230, 160, 40)),
    "SILVER": ([("XAG.INR.KG", 1)], "AG", (200, 210, 225)),
    "USDINR": ([(INR, 1)], "USD", FX),
    "EURINR": ([("EUR.USD.RATE", 1), (INR, 1)], "EUR", FX),
    "GBPINR": ([("GBP.USD.RATE", 1), (INR, 1)], "GBP", FX),
    "AEDINR": ([(INR, 1), ("USD.AED.RATE", -1)], "AED", FX),
    "SGDINR": ([(INR, 1), ("USD.SGD.RATE", -1)], "SGD", FX),
    "JPYINR": ([(INR, 1), ("USD.JPY.RATE", -1)], "JPY", FX),
    "NIFTY": ([("NIFTY50.INR.IDX", 1)], "N50", (255, 140, 90)),
    "BANKNIFTY": ([("NIFTYBANK.INR.IDX", 1)], "BNK", (255, 140, 90)),
    "BRENT": ([("BRENT.USD.BBL", 1)], "OIL", (170, 140, 110)),
}
NAMES = {"GOLD": "Gold 24K ₹/g", "GOLD22": "Gold 22K ₹/g", "SILVER": "Silver ₹/kg",
         "USDINR": "USD → ₹", "EURINR": "EUR → ₹", "GBPINR": "GBP → ₹", "AEDINR": "AED → ₹", "SGDINR": "SGD → ₹",
         "JPYINR": "JPY → ₹", "NIFTY": "Nifty 50", "BANKNIFTY": "Nifty Bank", "BRENT": "Brent $/bbl"}
TICKER = re.compile(r"^\^?[A-Z][A-Z0-9.\-]{0,9}$")
STOCK = (150, 160, 255)
UP, DOWN, FLAT, NONE = (70, 220, 110), (255, 80, 80), (210, 210, 220), (90, 90, 105)
MAX = 10
SHOWS = ("price", "change", "both")  # both: price, then +/- %, half of each page
COMPARES = {"prev": "previous close", "7d": "1 week ago", "30d": "1 month ago"}  # or a YYYY-MM-DD date
SNAPDATA = "https://snapdata.dev/api/v1/"
UA = {"User-Agent": "Mozilla/5.0 dotmatrix-unlocked"}


def valid(items) -> list[str]:
    """Config check: built-in ids or US tickers, deduped, at most MAX."""
    if not isinstance(items, list):
        raise ValueError("markets: a list")
    out = []
    for s in items:
        s = str(s).strip().upper()
        if not (s in SNAP or TICKER.match(s)):
            raise ValueError(f"markets: unknown {s!r}")
        if s not in out:
            out.append(s)
    return out[:MAX]


def valid_vs(v) -> str:
    v = str(v)
    if v in COMPARES:
        return v
    try:
        d = date.fromisoformat(v)
    except ValueError:
        raise ValueError("compare with: prev, 7d, 30d or a date") from None
    if not date(2000, 1, 1) <= d < date.today():
        raise ValueError("compare with: a past date")
    return v


def base_day(vs: str, today: date | None = None) -> date | None:
    """The day to compare against; None = previous close."""
    today = today or date.today()
    return None if vs == "prev" else today - timedelta(days=int(vs[:-1])) if vs in COMPARES else date.fromisoformat(vs)


def _get(url: str) -> dict:
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15).read())


def _dataset(iid: str) -> str:
    return ("gold/in" if iid.startswith("XAU.") else "silver/in" if iid.startswith("XAG.") else
            "fx/world" if iid.endswith(".RATE") else "equity-indices/in" if iid.endswith(".IDX") else "crude/world")


_series: dict[str, tuple[float, dict]] = {}  # dataset -> (fetched at, {iid: {date: value}}), last 30 days
_days: dict[tuple[str, str], dict] = {}      # (dataset, day) -> {iid: value}; days >48h old never change


def _rows(obs: list) -> dict:
    out = {}
    for o in obs:
        if o.get("value") is not None:
            out.setdefault(o["instrument_id"], {})[o["date"]] = o["value"]
    return out


def snap_on(iid: str, day: date) -> float | None:
    """Close on `day`, or the last trading day before it (weekends and holidays have no value)."""
    ds = _dataset(iid)
    if time.time() - _series.get(ds, (0, {}))[0] > 3600:
        _series[ds] = (time.time(), _rows(_get(f"{SNAPDATA}{ds}/series/30d.json")["observations"]))
    hist = _series[ds][1].get(iid, {})
    if hist and min(hist) <= day.isoformat():  # inside the 30-day window
        past = [d for d in hist if d <= day.isoformat()]
        return hist[max(past)] if past else None
    for back in range(7):  # older: one dated snapshot per day, walking back over closed days
        d = (day - timedelta(days=back)).isoformat()
        if (ds, d) not in _days:
            try:
                _days[(ds, d)] = {k: v[d] for k, v in _rows(_get(f"{SNAPDATA}{ds}/{d}.json")["observations"]).items()}
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                _days[(ds, d)] = {}
        if iid in _days[(ds, d)]:
            return _days[(ds, d)][iid]
    return None


def yahoo_on(sym: str, day: date) -> float | None:
    """US close on `day`, or the last trading day before it."""
    end = int(time.mktime((day + timedelta(days=1)).timetuple()))
    r = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
             f"?period1={end - 10 * 86400}&period2={end}&interval=1d")["chart"]["result"][0]
    closes = [c for c in (r.get("indicators", {}).get("quote") or [{}])[0].get("close") or [] if c is not None]
    return closes[-1] if closes else None


def snap_quote(obs: dict, terms: list) -> tuple[float, float | None] | None:
    """(value, change %) for a product of snapdata instruments; None if any is missing today."""
    v = p = 1.0
    for iid, power in terms:
        o = obs.get(iid) or {}
        if o.get("value") is None:
            return None
        v *= o["value"] ** power
        p = p * o["prev_close"] ** power if p and o.get("prev_close") else None
    return v, (v / p - 1) * 100 if p else None


def fetch(items: list[str], vs: str = "prev") -> dict[str, tuple[float | None, float | None]]:
    """id -> (value, change % against vs). Missing or failed ones are left out."""
    out, day = {}, base_day(vs)
    if any(i in SNAP for i in items):
        obs = {o["instrument_id"]: o for o in _get(f"{SNAPDATA}all/latest.json")["observations"]}
        for i in items:
            if i in SNAP and (q := snap_quote(obs, SNAP[i][0])):
                if day:
                    base = 1.0
                    for iid, power in SNAP[i][0]:
                        b = snap_on(iid, day)
                        base = base * b ** power if base and b else None
                    q = (q[0], (q[0] / base - 1) * 100 if base else None)
                out[i] = q
    for i in items:
        if i in SNAP:
            continue
        try:
            m = _get("https://query1.finance.yahoo.com/v8/finance/chart/"
                     f"{urllib.parse.quote(i)}?range=1d&interval=1d")["chart"]["result"][0]["meta"]
            price = float(m["regularMarketPrice"])
            prev = yahoo_on(i, day) if day else m.get("previousClose") or m.get("chartPreviousClose")
            out[i] = (price, (price / prev - 1) * 100 if prev else None)
        except Exception:
            pass  # unknown ticker or Yahoo hiccup: shows as --
    return out


def fmt(v: float, n: int) -> str:
    """Fit a number into n characters: fewer decimals first, then K/M."""
    for d in (2, 1, 0):
        s = f"{v:.{d}f}"
        if len(s) <= n:
            return s
    for div, suf in ((1e3, "K"), (1e6, "M"), (1e9, "B")):
        for d in (1, 0):
            s = f"{v / div:.{d}f}{suf}"
            if len(s) <= n:
                return s
    return "9" * n


def fmt_chg(c: float, n: int) -> str:
    """+0.26% / -1.2% / +12%: always signed, fitted to n characters."""
    sign, a = "+" if c >= 0 else "-", abs(c)
    small = ((2, "%"), (1, "%"), (2, ""), (1, ""), (0, "%"), (0, ""))  # keep the % while a decimal fits
    for d, pct in small if a < 10 else ((1, "%"), (0, "%"), (1, ""), (0, "")):
        s = f"{sign}{a:.{d}f}{pct}"
        if len(s) <= n:
            return s
    return sign + "9" * (n - 1)


ROWS = 5  # 6px rows of the 3x5 font


def frame(items: list[str], quotes: dict, t: float, page_secs: float = 5, show: str = "price") -> Image.Image:
    img = render.blank()
    if not items:
        render.draw_text(img, 2, 13, "ADD ONE", NONE)
        return img
    pages = [items[i:i + ROWS] for i in range(0, len(items), ROWS)]
    rows = pages[int(t // page_secs) % len(pages)]
    as_change = show == "change" or (show == "both" and t % page_secs >= page_secs / 2)
    pitch = 6 if len(rows) == ROWS else min(8, 32 // len(rows))
    y = (32 - pitch * len(rows) + (pitch - 5)) // 2
    for i in rows:
        label, colour = (SNAP[i][1], SNAP[i][2]) if i in SNAP else (render.clean(i)[:4], STOCK)
        v, chg = quotes.get(i, (None, None))
        n = min(5, 8 - len(label))  # 5 max keeps a gap after the label
        value = "--" if v is None else (fmt_chg(chg, n) if chg is not None else "0") if as_change else fmt(v, n)
        tone = NONE if v is None else FLAT if not chg else UP if chg > 0 else DOWN
        render.draw_text(img, 0, y, label, colour)
        render.draw_text(img, 32 - render.text_width(value), y, value, tone)
        y += pitch
    if len(pages) > 1:  # page dots along the bottom edge
        for p in range(len(pages)):
            img.putpixel((31 - 2 * (len(pages) - 1 - p), 31), FLAT if pages[p] is rows else NONE)
    return img


if __name__ == "__main__":
    assert valid(["gold", "aapl", "GOLD", "^gspc"]) == ["GOLD", "AAPL", "^GSPC"]
    for bad in (["AAPL; rm"], "GOLD"):
        try:
            valid(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    assert fmt(14804, 5) == "14804" and fmt(230000, 6) == "230000" and fmt(230000, 5) == "230K"
    assert fmt(94.9649, 5) == "94.96" and fmt(343.46, 4) == "343" and fmt(1234.6, 4) == "1235"
    assert fmt(22977.35, 5) == "22977" and fmt(0.5, 4) == "0.50"
    obs = {"USD.INR.RATE": {"value": 95.0, "prev_close": 94.0}, "EUR.USD.RATE": {"value": 1.1, "prev_close": 1.1},
           "USD.JPY.RATE": {"value": 158.0, "prev_close": None}}
    v, chg = snap_quote(obs, SNAP["EURINR"][0])
    assert round(v, 2) == 104.5 and round(chg, 2) == 1.06  # EUR->INR moves with USD->INR when EUR/USD is flat
    v, chg = snap_quote(obs, SNAP["JPYINR"][0])
    assert round(v, 4) == 0.6013 and chg is None and fmt(v, 5) == "0.60"  # no prev close -> no colour
    assert snap_quote(obs, SNAP["GBPINR"][0]) is None  # GBP missing today
    q = {"GOLD": (14804.0, 0.25), "SILVER": (230000.0, 0.0), "AAPL": (343.46, -1.2)}
    img = frame(["GOLD", "SILVER", "USDINR", "AAPL"], q, 0)
    assert img.size == (32, 32) and img.getpixel((31, img.height - 1)) == (0, 0, 0)
    colours = {img.getpixel((x, y)) for x in range(32) for y in range(32)}
    assert UP in colours and DOWN in colours and NONE in colours  # gold up, Apple down, USD/INR missing
    assert fmt_chg(0.2573, 5) == "+0.3%" and fmt_chg(0.2573, 6) == "+0.26%" and fmt_chg(-1.234, 4) == "-1.2"
    assert fmt_chg(-12.3, 5) == "-12%" and fmt_chg(250, 4) == "+250" and fmt_chg(-35, 5) == "-35%"
    assert base_day("prev") is None and base_day("7d", date(2026, 10, 19)) == date(2026, 10, 12)
    assert base_day("2026-01-02") == date(2026, 1, 2) and valid_vs("30d") == "30d"
    for bad in ("2099-01-01", "1d", "yesterday"):
        try:
            valid_vs(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    _series["gold/in"] = (time.time(), {"XAU.24K.INR.G": {"2026-10-09": 100.0, "2026-10-12": 110.0}})
    assert snap_on("XAU.24K.INR.G", date(2026, 10, 11)) == 100.0  # Sunday -> Friday's close
    assert snap_on("XAU.24K.INR.G", date(2026, 10, 12)) == 110.0
    a, b = frame(["GOLD"], {"GOLD": (14804.0, 0.26)}, 0, 4, "both"), frame(["GOLD"], {"GOLD": (14804.0, 0.26)}, 3, 4, "both")
    assert a.tobytes() != b.tobytes()  # both: price, then change
    assert frame(["GOLD"], {"GOLD": (1.0, -2.0)}, 0, 4, "change").tobytes() != frame(["GOLD"], {"GOLD": (1.0, 2.0)}, 0, 4, "change").tobytes()
    six = frame(list(SNAP)[:6], {}, 0), frame(list(SNAP)[:6], {}, 5)
    assert six[0].tobytes() != six[1].tobytes()  # pages flip
    print("markets ok")
