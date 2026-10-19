"""32x32 frame rendering with tiny bitmap fonts (3x5 regular, 3x4 small)."""
import math
from datetime import datetime
import unicodedata
from types import SimpleNamespace

from PIL import Image

# each glyph: 5 rows x 3 cols, row-major
FONT = {
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001001010010",
    "8": "111101111101111", "9": "111101111001111",
    "A": "010101111101101", "B": "110101110101110", "C": "011100100100011", "D": "110101101101110",
    "E": "111100110100111", "F": "111100110100100", "G": "011100101101011", "H": "101101111101101",
    "I": "111010010010111", "J": "001001001101010", "K": "101101110101101", "L": "100100100100111",
    "M": "101111111101101", "N": "110101101101101", "O": "010101101101010", "P": "110101110100100",
    "Q": "010101101110011", "R": "110101110101101", "S": "011100010001110", "T": "111010010010010",
    "U": "101101101101111", "V": "101101101101010", "W": "101101111111101", "X": "101101010101101",
    "Y": "101101010010010", "Z": "111001010100111",
    " ": "000000000000000", ":": "000010000010000", ".": "000000000000010", "-": "000000111000000",
    "°": "010101010000000", "%": "101001010100101", "/": "001001010100100", "!": "010010010000010",
    "?": "111001010000010", "'": "010010000000000", "&": "010101010101011", "+": "000010111010000",
    ",": "000000000010100", "(": "010100100100010", ")": "010001001001010",
}

# 3x4: one row shorter. Same glyph set as FONT; reads worse on E/F, B/8, S/5, but buys a third text line.
_SMALL = {
    "0": "111 101 101 111", "1": "110 010 010 111", "2": "110 001 010 111", "3": "111 011 001 111",
    "4": "101 101 111 001", "5": "111 110 001 110", "6": "100 111 101 111", "7": "111 001 010 010",
    "8": "111 111 101 111", "9": "111 101 111 001",
    "A": "010 101 111 101", "B": "110 110 101 110", "C": "011 100 100 011", "D": "110 101 101 110",
    "E": "111 110 100 111", "F": "111 100 110 100", "G": "011 100 101 011", "H": "101 111 101 101",
    "I": "111 010 010 111", "J": "001 001 101 010", "K": "101 110 101 101", "L": "100 100 100 111",
    "M": "111 111 101 101", "N": "110 101 101 101", "O": "010 101 101 010", "P": "110 101 110 100",
    "Q": "010 101 110 011", "R": "110 101 110 101", "S": "011 110 001 110", "T": "111 010 010 010",
    "U": "101 101 101 111", "V": "101 101 101 010", "W": "101 101 111 111", "X": "101 010 010 101",
    "Y": "101 101 010 010", "Z": "111 001 110 111",
    " ": "000 000 000 000", ":": "000 010 000 010", ".": "000 000 000 010", "-": "000 111 000 000",
    "°": "010 101 010 000", "%": "101 001 100 101", "/": "001 010 010 100", "!": "010 010 000 010",
    "?": "111 011 000 010", "'": "010 010 000 000", "&": "010 111 101 011", "+": "000 010 111 010",
    ",": "000 000 010 100", "(": "010 100 100 010", ")": "010 001 001 010",
}
FONTS = {"regular": (FONT, 5), "small": ({k: v.replace(" ", "") for k, v in _SMALL.items()}, 4)}


# Indian scripts share one layout (offset within each Unicode block), so one table romanises Tamil, Hindi,
# Telugu, Kannada, Malayalam, Bengali, Gujarati, Gurmukhi and Odia. Phonetic, not a formal scheme.
_IND_VOWEL = dict(zip(range(0x05, 0x15), "a aa i ii u uu ri - - e e ai - o o au".split()))
_IND_CONS = dict(zip(range(0x15, 0x3A), ("k kh g gh ng ch chh j jh ny t th d dh n t th d dh n n p ph b bh m y r r l l zh "
                                          "v sh sh s h").split()))
_IND_CONS |= dict(zip(range(0x58, 0x60), "q kh g z r rh f y".split())) | dict(zip(range(0x7A, 0x80), "n n r l l k".split()))
_IND_SIGN = dict(zip(range(0x3E, 0x4D), "aa i ii u uu ri - - e e ai - o o au".split()))
_IND_MISC = {0x01: "n", 0x02: "m", 0x03: "h", 0x64: ".", 0x65: "."} | {0x66 + d: str(d) for d in range(10)}


def indic(s: str) -> str:
    """Romanise Indian-script text: consonants carry an 'a' that a vowel sign replaces or a virama drops."""
    out, inherent, hindi = [], False, False
    for ch in unicodedata.normalize("NFC", s):
        cp = ord(ch)
        if not 0x0900 <= cp < 0x0D80:
            if inherent and hindi and not ch.isalpha():  # Hindi drops a word's last 'a': kamal, not kamala
                out[-1] = out[-1][:-1]
            out.append(ch); inherent = False
            continue
        o, hindi = cp & 0x7F, cp < 0x0A00
        if o in _IND_CONS:
            out.append(_IND_CONS[o] + "a"); inherent = True
            continue
        if inherent and (o in _IND_SIGN or o == 0x4D):  # vowel sign or virama replaces the inherent 'a'
            out[-1] = out[-1][:-1] + _IND_SIGN.get(o, "").replace("-", "")
        elif o in _IND_VOWEL or o in _IND_MISC:
            out.append((_IND_VOWEL.get(o) or _IND_MISC.get(o, "")).replace("-", ""))
        inherent = False
    if inherent and hindi:
        out[-1] = out[-1][:-1]
    return "".join(out)


def clean(s: str) -> str:
    """Uppercase, romanise Indian scripts, strip accents, drop anything the font can't draw."""
    s = unicodedata.normalize("NFKD", indic(s)).encode("ascii", "ignore").decode().upper()
    return "".join(c for c in s if c in FONT)


def text_width(s: str, scale: int = 1) -> int:
    return max(0, len(s) * 4 - 1) * scale


def draw_text(img: Image.Image, x: int, y: int, s: str, color, scale: int = 1, font: str = "regular") -> None:
    px = img.load()
    glyphs, h = FONTS[font]
    for i, ch in enumerate(s.upper()):
        bits = glyphs.get(ch, glyphs["?"])
        for r in range(h):
            for c in range(3):
                if bits[r * 3 + c] == "1":
                    for dy in range(scale):
                        for dx in range(scale):
                            X, Y = x + (i * 4 + c) * scale + dx, y + r * scale + dy
                            if 0 <= X < 32 and 0 <= Y < 32:
                                px[X, Y] = color


def blank(bg=(0, 0, 0)) -> Image.Image:
    return Image.new("RGB", (32, 32), tuple(bg))


def wrap(text: str, n: int) -> list[str]:
    """Word-wrap to lines of <= n chars, hard-splitting long words."""
    lines, cur = [], ""
    for word in text.split():
        while len(word) > n:
            if cur:
                lines.append(cur); cur = ""
            lines.append(word[:n]); word = word[n:]
        if len(cur) + len(word) + (1 if cur else 0) <= n:
            cur = f"{cur} {word}" if cur else word
        else:
            lines.append(cur); cur = word
    return lines + [cur] if cur else lines


def _sprite(img, x, y, rows, pal):
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch in pal and 0 <= x + c < 32 and 0 <= y + r < 32:
                img.putpixel((x + c, y + r), pal[ch])


# 7x5 weather icons
PAL = {"Y": (255, 200, 0), "W": (200, 200, 210), "G": (110, 110, 120), "B": (60, 140, 255), "M": (220, 220, 160)}
SUN = [".Y.Y.Y.", "..YYY..", "YYYYYYY", "..YYY..", ".Y.Y.Y."]
MOON = ["..MMM..", ".MM....", ".MM....", ".MM....", "..MMM.."]
CLOUD = [".......", "..WW...", ".WWWW..", "WWWWWWW", ".WWWWW."]
PARTLY_DAY = ["....Y.Y", "..WWYY.", ".WWWWY.", "WWWWWWW", ".WWWWW."]
PARTLY_NIGHT = ["....MM.", "..WWM..", ".WWWWM.", "WWWWWWW", ".WWWWW."]
RAIN = [".GGGG..", "GGGGGGG", ".GGGGG.", ".B.B.B.", "B.B.B.."]
SNOW = [".GGGG..", "GGGGGGG", ".GGGGG.", ".W.W.W.", "W.W.W.."]
STORM = [".GGGG..", "GGGGGGG", ".GGGGG.", "...YY..", "..YY..."]
FOG = ["GGGGGGG", ".......", "GGGGGGG", ".......", "GGGGGGG"]


def weather_icon(code: int, is_day: bool) -> list[str]:
    """WMO weather code -> icon. https://open-meteo.com/en/docs (weather_code)."""
    if code == 0:
        return SUN if is_day else MOON
    if code in (1, 2):
        return PARTLY_DAY if is_day else PARTLY_NIGHT
    if code == 3:
        return CLOUD
    if code in (45, 48):
        return FOG
    if 71 <= code <= 77 or code in (85, 86):
        return SNOW
    if code >= 95:
        return STORM
    return RAIN


def weather_word(code: int) -> str:
    if code == 0: return "CLEAR"
    if code in (1, 2): return "FAIR"
    if code == 3: return "CLOUDY"
    if code in (45, 48): return "FOG"
    if 51 <= code <= 57: return "DRIZZLE"
    if 71 <= code <= 77 or code in (85, 86): return "SNOW"
    if 80 <= code <= 82: return "SHOWERS"
    if code >= 95: return "STORM"
    return "RAIN"


CLAUDE = (217, 119, 87)
ASK = (255, 200, 0)
DIM = (70, 75, 95)
DIVIDER = (45, 45, 60)
SPOTIFY = (30, 215, 96)
SPARK = [["..O..", "O.O.O", ".OOO.", "O.O.O", "..O.."],   # + arms
         ["O...O", ".O.O.", "..O..", ".O.O.", "O...O"]]   # x arms
CLAUDE_DIM = (110, 60, 45)
SESSION_COLORS = {"input": ASK, "working": CLAUDE, "waiting": (90, 95, 120)}


def music_pages(music: dict, n: int = 2, title_color=(235, 235, 235)) -> list[tuple[tuple, list[str]]]:
    """Title then main artist (green), each as pages of n lines x 8 chars."""
    artist = music["artist"].split(",")[0].split("&")[0].split(" feat")[0].strip()
    pages = []
    for text, color in ((music["title"], tuple(title_color)), (artist, SPOTIFY)):
        lines = wrap(" ".join(w[:8] for w in clean(text).split()), 8)  # clip long words, don't spill to a 3rd line
        pages += [(color, lines[i:i + n]) for i in range(0, len(lines), n)]
    return pages


# Dashboard = vertical stack of modules, top to bottom, 1px gap between them; music takes whatever is left.
# To add a module: write a draw fn and add an entry to MODULES. The web UI picks it up from GET /modules.
def _clock(img, y, m, c):
    hh = f"{c.now:%H}" if c.cfg["clock_24h"] else f"{(c.now.hour % 12) or 12:2d}"
    draw_text(img, 0, y, f"{hh}:{c.now:%M}", c.col, font=m["font"])
    if "weather" in c.on and c.weather:
        _sprite(img, 25, y, weather_icon(c.weather["code"], c.weather["is_day"]), PAL)


def _weather(img, y, m, c):
    if c.weather:
        draw_text(img, 0, y, f"{round(c.weather['temp'])}°", c.col, font=m["font"])
    if "clock" in c.on or not c.weather:
        draw_text(img, 21, y, f"{c.now:%a}".upper(), DIM, font=m["font"])
    else:  # no clock row to carry the icon
        _sprite(img, 25, y, weather_icon(c.weather["code"], c.weather["is_day"]), PAL)


def _divider(img, y, m, c):
    sweep = "working" in c.sessions and "input" not in c.sessions and "claude" in c.on
    span = 32 - 4
    pos = c.tick % (2 * span)
    x0 = pos if pos < span else 2 * span - pos
    lit = c.claude_color
    glow = tuple(v * 28 // 100 for v in lit)
    for x in range(32):  # while working the divider becomes a 4px light bouncing left/right
        img.putpixel((x, y), (lit if 0 <= x - x0 < 4 else glow) if sweep else c.col)


def _claude(img, y, m, c):
    font, ty = m["font"], y + (5 - FONTS[m["font"]][1]) // 2  # center the label on the 5px spark
    if "input" in c.sessions:
        lit = c.tick % 2 == 0
        _sprite(img, 0, y, SPARK[0], {"O": ASK if lit else DIM})
        if lit:
            draw_text(img, 7, ty, "ASK!", ASK, font=font)
    elif "working" in c.sessions:
        _sprite(img, 0, y, SPARK[c.tick % 2], {"O": c.col})
        draw_text(img, 7, ty, "WORK", c.col, font=font)
    elif c.sessions:
        _sprite(img, 0, y, SPARK[0], {"O": CLAUDE_DIM})
        draw_text(img, 7, ty, "DONE", DIM, font=font)
    else:
        _sprite(img, 0, y, SPARK[0], {"O": (40, 30, 28)})
    order = {"input": 0, "working": 1, "waiting": 2}
    for i, st in enumerate(sorted(c.sessions, key=order.get)[:4]):  # one 2x2 dot per session, max 4
        for dx in (0, 1):
            for dy in (0, 1):
                img.putpixel((30 - i * 3 + dx, y + 1 + dy), SESSION_COLORS[st])


def _date(img, y, m, c):
    s = f"{c.now.day} {c.now:%b}".upper()
    draw_text(img, (32 - text_width(s)) // 2, y, s, c.col, font=m["font"])


def _music(img, y, m, c):
    h = FONTS[m["font"]][1]
    pages = music_pages(c.music, c.lines, c.col) if c.music and c.lines else []
    if pages:
        pc, lines = pages[int(c.t / c.cfg["page_secs"]) % len(pages)]
    else:  # nothing playing: date + weather word, dimmed
        pc = DIM
        lines = ([] if "date" in c.on else [f"{c.now.day} {c.now:%b}".upper()]) + \
                ([weather_word(c.weather["code"])] if "weather" in c.on and c.weather else [])
        lines = [" " * ((8 - len(s)) // 2) + s for s in lines[:c.lines]]  # roughly centered
    for i, line in enumerate(lines):
        draw_text(img, 0, y + i * (h + 1), line, pc, font=m["font"])


def _bigclock(img, y, m, c):  # 2x digits: 6x10 each, fills the width
    hh = f"{c.now:%H}" if c.cfg["clock_24h"] else f"{(c.now.hour % 12) or 12:2d}"
    for ch, x in zip(hh + f"{c.now:%M}", (1, 8, 18, 25)):
        if ch != " ":
            draw_text(img, x, y, ch, c.col, scale=2)
    for dy in (2, 6):  # colon
        for dx in (0, 1):
            for yy in (0, 1):
                img.putpixel((15 + dx, y + dy + yy), c.col)


def _line(img, x0, y0, x1, y1, col):
    n = int(max(abs(x1 - x0), abs(y1 - y0), 1) * 2)
    for k in range(n + 1):
        x, yy = round(x0 + (x1 - x0) * k / n), round(y0 + (y1 - y0) * k / n)
        if 0 <= x < 32 and 0 <= yy < 32:
            img.putpixel((x, yy), col)


def _analog(img, y, m, c):  # round face on the left, weekday + day on the right
    cx, cy = 7, y + 7
    for k in range(60):
        a = 2 * math.pi * k / 60
        img.putpixel((round(cx + 7 * math.cos(a)), round(cy + 7 * math.sin(a))), DIVIDER if k % 15 else DIM)
    h = (c.now.hour % 12 + c.now.minute / 60) / 12 * 2 * math.pi - math.pi / 2
    mi = c.now.minute / 60 * 2 * math.pi - math.pi / 2
    _line(img, cx, cy, cx + 6 * math.cos(mi), cy + 6 * math.sin(mi), (235, 235, 235))
    _line(img, cx, cy, cx + 4 * math.cos(h), cy + 4 * math.sin(h), c.col)
    draw_text(img, 18, y + 2, f"{c.now:%a}".upper(), DIM, font=m["font"])
    draw_text(img, 18, y + 9, f"{c.now.day:02d}", c.col, font=m["font"])


def _binary(img, y, m, c):  # BCD: one column per digit of HHMM, 2x2 dots, ones at the bottom
    for col, (digit, x) in enumerate(zip(f"{c.now:%H%M}", (6, 11, 18, 23))):
        for bit in range(4):
            lit = int(digit) >> bit & 1
            for dx in (0, 1):
                for dy in (0, 1):
                    img.putpixel((x + dx, y + 9 - bit * 3 + dy), c.col if lit else (35, 32, 45))


def _week(img, y, m, c):
    today = c.now.weekday()
    for i, ch in enumerate("MTWTFSS"):
        col = c.col if i == today else (45, 45, 60) if i >= 5 else DIM
        draw_text(img, 2 + i * 4, y, ch, col, font=m["font"])


def _month(img, y, m, c):  # one dot per day, Monday first; today lit, past days dim
    first = c.now.replace(day=1)
    days = ((first.replace(month=first.month % 12 + 1, year=first.year + first.month // 12)) - first).days
    off = first.weekday()
    for d in range(days):
        r, k = divmod(off + d, 7)
        x, yy = 2 + k * 4, y + r * 4
        col = c.col if d + 1 == c.now.day else (45, 45, 60) if d + 1 < c.now.day else \
              (110, 90, 130) if k >= 5 else (130, 130, 150)
        for dx in (0, 1):
            for dy in (0, 1):
                img.putpixel((x + dx, yy + dy), col)


def _progress(img, y, m, c):  # how much of the day is gone
    f = (c.now.hour * 60 + c.now.minute) / 1440
    for x in range(32):
        for dy in (0, 1):
            img.putpixel((x, y + dy), c.col if x < round(f * 32) else (35, 32, 45))


def _forecast(img, y, m, c):  # next hours of temperature as bars (one per hour)
    temps = (c.weather or {}).get("hourly") or []
    temps = temps[:8]
    if not temps:
        return
    lo, hi = min(temps), max(temps)
    for i, t in enumerate(temps):
        h = 1 + round((t - lo) / max(hi - lo, 1) * 7)
        for x in range(3):
            for dy in range(h):
                img.putpixel((i * 4 + x, y + 7 - dy), c.col if i else (255, 255, 255))


def _sun(img, y, m, c):  # next sunrise or sunset
    sun = (c.weather or {}).get("sun")
    if not sun:
        return
    now = c.now.replace(tzinfo=None)
    events = sorted([(datetime.fromisoformat(t), "rise") for t in sun["rise"]] +
                    [(datetime.fromisoformat(t), "set") for t in sun["set"]])
    nxt = next(((t, k) for t, k in events if t > now), None)
    if not nxt:
        return
    t, kind = nxt
    col = (255, 200, 0) if kind == "rise" else (255, 110, 40)
    _sprite(img, 0, y, ["..Y..", ".YYY.", "YYYYY"] if kind == "rise" else ["YYYYY", ".YYY.", "..Y.."], {"Y": col})
    for x in range(7):
        img.putpixel((x, y + 4), (60, 50, 70))  # horizon
    draw_text(img, 12, y, f"{t:%H:%M}", c.col, font=m["font"])


def _moon(img, y, m, c):  # phase from the date alone, no network
    days = (c.now.replace(tzinfo=None) - datetime(2000, 1, 6, 18, 14)).total_seconds() / 86400
    p = days / 29.530588853 % 1
    for dy in range(7):
        for dx in range(7):
            u, v = (dx - 3) / 3.3, (dy - 3) / 3.3
            if u * u + v * v > 1:
                continue
            edge = math.cos(2 * math.pi * p) * math.sqrt(max(0.0, 1 - v * v))
            lit = u > edge if p < 0.5 else u < -edge
            img.putpixel((3 + dx, y + dy), (235, 230, 200) if lit else (40, 38, 50))
    draw_text(img, 14, y + 1, f"{round((1 - math.cos(2 * math.pi * p)) / 2 * 100)}%", c.col, font=m["font"])


# India's NAQI PM2.5 bands (µg/m³): good, satisfactory, moderate, poor, very poor, severe
AIR_BANDS = [(30, (70, 220, 110)), (60, (170, 220, 80)), (90, (255, 200, 0)), (120, (255, 130, 40)),
             (250, (255, 60, 60)), (float("inf"), (170, 30, 60))]


def _air(img, y, m, c):  # PM2.5 near the weather city (Indian cities, CPCB stations); blank elsewhere
    pm = (c.weather or {}).get("pm25")
    if pm is None:
        return
    draw_text(img, 0, y, "AIR", c.col, font=m["font"])
    v = str(round(pm))
    draw_text(img, 32 - text_width(v), y, v, next(col for top, col in AIR_BANDS if pm <= top), font=m["font"])


# height: "font" = the module's font height, int = fixed px, None = takes the remaining space (one per layout)
MODULES = {
    "clock":   {"label": "Clock", "height": "font", "font": True, "color": [255, 170, 60], "draw": _clock},
    "weather": {"label": "Weather · temp + day", "height": "font", "font": True, "color": [255, 255, 255], "draw": _weather},
    "date":    {"label": "Date", "height": "font", "font": True, "color": list(DIM), "draw": _date},
    "divider": {"label": "Divider · sweeps while Claude works", "height": 1, "font": False, "color": list(DIVIDER), "draw": _divider},
    "claude":  {"label": "Claude activity", "height": 5, "font": True, "color": list(CLAUDE), "draw": _claude},
    "music":   {"label": "Now playing · or date", "height": None, "font": True, "color": [235, 235, 235], "draw": _music},
    "spacer":  {"label": "Spacer", "height": 2, "font": False, "color": [0, 0, 0], "draw": lambda *a: None},
    "bigclock": {"label": "Big clock", "height": 10, "font": False, "color": [255, 170, 60], "draw": _bigclock},
    "analog":  {"label": "Analog clock · with day", "height": 15, "font": True, "color": [255, 170, 60], "draw": _analog},
    "binary":  {"label": "Binary clock · HH MM", "height": 11, "font": False, "color": [80, 220, 140], "draw": _binary},
    "week":    {"label": "Week · today lit", "height": "font", "font": True, "color": [255, 170, 60], "draw": _week},
    "month":   {"label": "Month · a dot per day", "height": 23, "font": False, "color": [255, 170, 60], "draw": _month},
    "progress": {"label": "Day progress bar", "height": 2, "font": False, "color": [217, 119, 87], "draw": _progress},
    "forecast": {"label": "Forecast · next 8 hours", "height": 8, "font": False, "color": [90, 160, 255], "draw": _forecast},
    "sun":     {"label": "Next sunrise / sunset", "height": "font", "font": True, "color": [235, 235, 235], "draw": _sun},
    "air":     {"label": "Air · PM2.5 near you (India)", "height": "font", "font": True, "color": [150, 150, 170], "draw": _air},
    "moon":    {"label": "Moon phase", "height": 7, "font": True, "color": [200, 200, 220], "draw": _moon},
}


def _m(id_, font="regular", color=None, on=True):
    return {"id": id_, "on": on, "font": font, "color": list(color or MODULES[id_]["color"])}


# Ready-made dashboards: loaded into the draft from the web UI, then tweak and Apply (or save as your own).
LAYOUTS = {
    "Classic": [_m("clock"), _m("weather"), _m("divider"), _m("claude"), _m("music")],
    "Big clock": [_m("bigclock"), _m("spacer"), _m("week"), _m("progress"), _m("music")],
    "Focus": [_m("bigclock", color=(235, 235, 235)), _m("divider"), _m("claude"), _m("progress"), _m("week", "small")],
    "Weather station": [_m("clock"), _m("weather"), _m("forecast"), _m("spacer"), _m("sun")],
    "Night owl": [_m("bigclock", color=(170, 40, 30)), _m("spacer"), _m("moon", color=(120, 110, 140)),
                  _m("date", color=(60, 50, 70))],
    "Binary": [_m("binary"), _m("spacer"), _m("date", color=(120, 120, 140)), _m("progress", color=(80, 220, 140)),
               _m("week", "small", color=(80, 220, 140))],
    "Analog": [_m("analog"), _m("week", "small"), _m("progress"), _m("music", "small")],
    "Calendar": [_m("clock"), _m("month")],
    "Now playing": [_m("clock", "small"), _m("divider"), _m("music", color=(255, 255, 255))],
    "Claude ops": [_m("claude"), _m("divider"), _m("clock", "small"), _m("weather", "small"), _m("music", "small")],
    "Minimal": [_m("spacer"), _m("spacer"), _m("bigclock", color=(235, 235, 235)), _m("spacer"),
                _m("date", color=(90, 90, 110))],
    "Week glance": [_m("date", color=(235, 235, 235)), _m("week"), _m("progress"), _m("forecast"),
                    _m("music", "small")],
}


DEFAULT_LAYOUT = LAYOUTS["Classic"]


def _height(m: dict) -> int:
    h = MODULES[m["id"]]["height"]
    return FONTS[m["font"]][1] if h == "font" else h


def dashboard(now, t: float, cfg: dict, weather: dict | None, sessions: list[str], music: dict | None) -> Image.Image:
    """Default stack (regular fonts):
    y=1  HH:MM ......... [icon]      y=7  27° ........... SUN
    y=13 ---- divider ----           y=15 [spark] WORK ...... dots    (divider sweeps while working; one dot per Claude session)
    y=21-31 song title / artist pages, or date + weather word when nothing plays
    t (unix time) drives animation; same t -> same frame, so unchanged frames aren't re-sent.
    """
    img = blank()
    mods = [m for m in cfg["layout"] if m["on"]]
    flex = next((m for m in mods if _height(m) is None), None)
    fixed = sum(_height(m) + 1 for m in mods if m is not flex)

    def lines_fit(margin):  # how many lines the flexible module gets
        return 0 if not flex else max(0, (32 - margin - fixed + 1) // (FONTS[flex["font"]][1] + 1))
    y = 1 if lines_fit(1) == lines_fit(0) else 0  # drop the top margin when it buys another line
    claude = next((m for m in cfg["layout"] if m["id"] == "claude"), None)
    c = SimpleNamespace(now=now, t=t, cfg=cfg, weather=weather, sessions=sessions, music=music,
                        on={m["id"] for m in mods}, tick=int(t * cfg["anim_fps"]), lines=lines_fit(y),
                        claude_color=tuple(claude["color"]) if claude else CLAUDE)
    for m in mods:
        if y > 31:
            break
        c.col = tuple(m["color"])
        MODULES[m["id"]]["draw"](img, y, m, c)
        h = _height(m)
        y += (c.lines * (FONTS[m["font"]][1] + 1) - 1 if h is None else h) + 1
    return img


def timer(remaining: float, total: float, label: str, t: float) -> Image.Image:
    """Countdown: M:SS (or H:MM past an hour) in the middle, a ring around the edge that drains clockwise
    from the top-left, label underneath. At zero it flashes TIME UP."""
    img = blank()
    if remaining <= 0:
        on = int(t * 2) % 2 == 0
        for i, s in enumerate(("TIME", "UP!")):
            draw_text(img, (32 - text_width(s)) // 2, 9 + i * 8, s, ASK if on else CLAUDE)
        return img
    secs = int(remaining + 0.999)  # 0.4s left still reads 0:01
    s = f"{secs // 3600}:{secs // 60 % 60:02d}" if secs >= 3600 else f"{secs // 60}:{secs % 60:02d}"
    color = (255, 255, 255) if remaining > 10 else ASK if remaining > 3 else (240, 60, 50)
    draw_text(img, (32 - text_width(s)) // 2, 10, s, color)
    lab = clean(label)[:6]
    draw_text(img, (32 - text_width(lab)) // 2, 18, lab, DIM)
    ring = [(x, 0) for x in range(32)] + [(31, y) for y in range(1, 32)] + \
           [(x, 31) for x in range(30, -1, -1)] + [(0, y) for y in range(30, 0, -1)]
    lit = math.ceil(len(ring) * remaining / max(total, 1))
    for i, p in enumerate(ring):
        img.putpixel(p, CLAUDE if i < lit else (40, 26, 22))
    return img


def message(text: str, color=(255, 255, 255), bg=(0, 0, 0)) -> Image.Image:
    """Word-wrapped text, 8 chars x 5 lines, centered."""
    lines = wrap(clean(text), 8)[:5]
    img = blank(bg)
    y = (32 - (len(lines) * 6 - 1)) // 2
    for i, line in enumerate(lines):
        draw_text(img, (32 - text_width(line)) // 2, y + i * 6, line, tuple(color))
    return img


def hello() -> Image.Image:
    img = blank()
    colors = [(255, 60, 60), (255, 160, 0), (255, 230, 0), (60, 220, 90), (60, 140, 255)]
    x = (32 - text_width("HELLO")) // 2
    for i, ch in enumerate("HELLO"):
        draw_text(img, x + i * 4, 13, ch, colors[i])
    return img


def test_pattern() -> Image.Image:
    """Color bars + white border + red top-left marker: checks orientation and RGB order."""
    img = blank()
    px = img.load()
    bars = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 255, 255), (128, 128, 128)]
    for y in range(32):
        for x in range(32):
            if x in (0, 31) or y in (0, 31):
                px[x, y] = (255, 255, 255)
            elif y < 24:
                px[x, y] = bars[(x - 1) * 8 // 30]
            else:
                v = (x - 1) * 255 // 29  # grayscale ramp
                px[x, y] = (v, v, v)
    for y in range(1, 4):
        for x in range(1, 4):
            px[x, y] = (255, 0, 0)
    return img


DEFAULT_CFG = {"layout": DEFAULT_LAYOUT, "clock_24h": True, "anim_fps": 1.0, "page_secs": 3.0}

if __name__ == "__main__":
    from datetime import datetime
    assert all(len(v) == 15 for v in FONT.values())
    small = FONTS["small"][0]
    assert small.keys() == FONT.keys() and all(len(v) == 12 for v in small.values())
    assert len(set(small.values())) == len(small) - 0, "small glyphs must be distinct"
    assert clean("Beyoncé – Halo!") == "BEYONCE  HALO!"
    assert clean("ஒரு நாள்") == "ORU NAAL" and clean("தமிழ்") == "TAMIZH" and clean("கண்ணே") == "KANNE"
    assert clean("दिल से") == "DIL SE" and clean("ಪ್ರೀತಿ") == "PRIITI" and clean("Song (ப்ரேமம்)") == "SONG (PREMAM)"
    assert wrap("HELLO WORLD ABCDEFGHIJ", 7) == ["HELLO", "WORLD", "ABCDEFG", "HIJ"]
    n, w = datetime(2026, 10, 18, 22, 15), {"temp": 27.4, "code": 3, "is_day": False}
    song = {"title": "Blinding Lights", "artist": "The Weeknd"}
    a = dashboard(n, 0, DEFAULT_CFG, w, ["working"], song)
    b = dashboard(n, 1, DEFAULT_CFG, w, ["working"], song)
    assert a.tobytes() != b.tobytes()  # working animates
    assert a.getpixel((0, 13)) == CLAUDE and b.getpixel((0, 13)) != CLAUDE  # sweep moved
    assert dashboard(n, 0, DEFAULT_CFG, w, [], None).tobytes() == dashboard(n, 1, DEFAULT_CFG, w, [], None).tobytes()
    assert music_pages({"title": "One Name", "artist": "Anirudh Ravichander, Super Subu"}, 2) == [
        ((235, 235, 235), ["ONE NAME"]), (SPOTIFY, ["ANIRUDH", "RAVICHAN"])]
    tiny = {**DEFAULT_CFG, "layout": [{**m, "font": "small"} for m in DEFAULT_LAYOUT]}
    long = {"title": "A Very Long Song Title Here", "artist": "X"}
    assert dashboard(n, 0, tiny, w, [], None).getpixel((0, 10)) == DIVIDER  # small fonts drop the top margin
    img = dashboard(n, 0, tiny, w, [], long)
    assert img.crop((0, 28, 32, 32)).getbbox()  # third song line drawn at y=28
    # reorder: music first, clock last
    flip = {**DEFAULT_CFG, "layout": DEFAULT_LAYOUT[::-1]}
    assert dashboard(n, 0, flip, w, [], long).crop((0, 0, 32, 5)).getbbox()
    off = {**DEFAULT_CFG, "layout": [{**m, "on": m["id"] == "clock"} for m in DEFAULT_LAYOUT]}
    assert dashboard(n, 0, off, w, [], long).crop((0, 7, 32, 32)).getbbox() is None
    few = {**DEFAULT_CFG, "layout": [DEFAULT_LAYOUT[0], {"id": "date", "on": True, "font": "small", "color": [9, 9, 9]},
                                     {"id": "spacer", "on": True, "font": "regular", "color": [0, 0, 0]}, DEFAULT_LAYOUT[4]]}
    img = dashboard(n, 0, few, w, [], long)
    assert {img.getpixel((x, 7)) for x in range(32)} >= {(9, 9, 9)}  # added date module drawn below clock
    rich = {**w, "hourly": [24, 25, 27, 28, 27, 26, 25, 24], "sun": {"rise": ["2026-10-18T06:02", "2026-10-19T06:02"],
                                                                     "set": ["2026-10-18T18:01", "2026-10-19T18:01"]}}
    for name, layout in LAYOUTS.items():
        img = dashboard(n, 0, {**DEFAULT_CFG, "layout": layout}, rich, ["working"], song)
        fixed = sum(_height(mm) + 1 for mm in layout if _height(mm) is not None)
        assert fixed <= 33 and img.getbbox(), name  # everything fits on 32 rows and draws something
    air = dashboard(n, 0, {**DEFAULT_CFG, "layout": [_m("air")]}, {**w, "pm25": 95.4}, [], None)
    assert (255, 130, 40) in {air.getpixel((x, y)) for x in range(32) for y in range(8)}  # 95 = poor = orange
    assert dashboard(n, 0, {**DEFAULT_CFG, "layout": [_m("air")]}, w, [], None).getbbox() is None  # no reading: blank
    many = {**DEFAULT_CFG, "layout": DEFAULT_LAYOUT * 3}
    dashboard(n, 0, many, w, ["working"], long)  # overflow just clips
    assert timer(90, 120, "tea", 0).getpixel((0, 0)) == CLAUDE and timer(90, 120, "tea", 0).getpixel((0, 1)) != CLAUDE
    assert timer(0, 120, "", 0).getbbox()
    assert message("needs input now please").getbbox() and hello().getbbox()
    assert test_pattern().getpixel((2, 2)) == (255, 0, 0)
    print("ok")
