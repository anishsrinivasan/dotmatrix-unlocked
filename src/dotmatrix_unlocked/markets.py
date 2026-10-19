"""Markets skin: rows of LABEL  VALUE, green up / red down on the day.

Indian bullion (IBJA), USD/INR (ECB), Nifty and Brent come from snapdata.dev: free, no key, daily.
US stocks come from Yahoo's chart endpoint: free, no key, unofficial (ponytail: if Yahoo locks it down,
swap in a keyed provider such as Finnhub here; nothing else changes)."""
import json
import re
import urllib.parse
import urllib.request

from PIL import Image

from . import render

# id -> (snapdata instrument, panel label, label colour)
SNAP = {
    "GOLD": ("XAU.24K.INR.G", "AU", (255, 190, 40)),
    "GOLD22": ("XAU.22K.INR.G", "22K", (230, 160, 40)),
    "SILVER": ("XAG.INR.KG", "AG", (200, 210, 225)),
    "USDINR": ("USD.INR.RATE", "USD", (120, 200, 255)),
    "NIFTY": ("NIFTY50.INR.IDX", "N50", (255, 140, 90)),
    "BANKNIFTY": ("NIFTYBANK.INR.IDX", "BNK", (255, 140, 90)),
    "BRENT": ("BRENT.USD.BBL", "OIL", (170, 140, 110)),
}
NAMES = {"GOLD": "Gold 24K ₹/g", "GOLD22": "Gold 22K ₹/g", "SILVER": "Silver ₹/kg", "USDINR": "USD → ₹",
         "NIFTY": "Nifty 50", "BANKNIFTY": "Nifty Bank", "BRENT": "Brent $/bbl"}
TICKER = re.compile(r"^\^?[A-Z][A-Z0-9.\-]{0,9}$")
STOCK = (150, 160, 255)
UP, DOWN, FLAT, NONE = (70, 220, 110), (255, 80, 80), (210, 210, 220), (90, 90, 105)
MAX = 10
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


def _get(url: str) -> dict:
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15).read())


def fetch(items: list[str]) -> dict[str, tuple[float | None, float | None]]:
    """id -> (value, change % on the day). Missing or failed ones are left out."""
    out = {}
    if any(i in SNAP for i in items):
        obs = {o["instrument_id"]: o for o in _get("https://snapdata.dev/api/v1/all/latest.json")["observations"]}
        for i in items:
            o = i in SNAP and obs.get(SNAP[i][0])
            if o and o.get("value") is not None:
                chg = o.get("change_pct")
                if chg is None and o.get("prev_close"):
                    chg = (o["value"] / o["prev_close"] - 1) * 100
                out[i] = (float(o["value"]), chg)
    for i in items:
        if i in SNAP:
            continue
        try:
            m = _get("https://query1.finance.yahoo.com/v8/finance/chart/"
                     f"{urllib.parse.quote(i)}?range=1d&interval=1d")["chart"]["result"][0]["meta"]
            prev = m.get("previousClose") or m.get("chartPreviousClose")
            out[i] = (float(m["regularMarketPrice"]), (m["regularMarketPrice"] / prev - 1) * 100 if prev else None)
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


ROWS = 5  # 6px rows of the 3x5 font


def frame(items: list[str], quotes: dict, t: float, page_secs: float = 5) -> Image.Image:
    img = render.blank()
    if not items:
        render.draw_text(img, 2, 13, "ADD ONE", NONE)
        return img
    pages = [items[i:i + ROWS] for i in range(0, len(items), ROWS)]
    rows = pages[int(t // page_secs) % len(pages)]
    pitch = 6 if len(rows) == ROWS else min(8, 32 // len(rows))
    y = (32 - pitch * len(rows) + (pitch - 5)) // 2
    for i in rows:
        label, colour = (SNAP[i][1], SNAP[i][2]) if i in SNAP else (render.clean(i)[:4], STOCK)
        v, chg = quotes.get(i, (None, None))
        value = fmt(v, min(5, 8 - len(label))) if v is not None else "--"  # 5 max keeps a gap after the label
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
    q = {"GOLD": (14804.0, 0.25), "SILVER": (230000.0, 0.0), "AAPL": (343.46, -1.2)}
    img = frame(["GOLD", "SILVER", "USDINR", "AAPL"], q, 0)
    assert img.size == (32, 32) and img.getpixel((31, img.height - 1)) == (0, 0, 0)
    colours = {img.getpixel((x, y)) for x in range(32) for y in range(32)}
    assert UP in colours and DOWN in colours and NONE in colours  # gold up, Apple down, USD/INR missing
    six = frame(list(SNAP)[:6], {}, 0), frame(list(SNAP)[:6], {}, 5)
    assert six[0].tobytes() != six[1].tobytes()  # pages flip
    print("markets ok")
