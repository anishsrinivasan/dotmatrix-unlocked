"""Time-synced lyrics for whatever is playing, from LRCLIB (free, no key), kept in step with the
play position the OS reports. Works with Spotify or any player the now-playing helper sees."""
import bisect
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

from . import render

LRCLIB = "https://lrclib.net/api/"
UA = {"User-Agent": "dotmatrix-unlocked (https://github.com/anishsrinivasan/dotmatrix-unlocked)"}
STAMP = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
NOISE = re.compile(r"\s+-\s+.*$|\s*[(\[](feat|with|ft)\.?\s[^)\]]*[)\]]", re.I)  # "Song - Remastered 2011", "(feat. X)"
WHITE = (255, 255, 255)
PALETTE = [(255, 60, 160), (0, 210, 255), (255, 190, 0), (130, 255, 60), (180, 100, 255), (255, 110, 60)]  # one per line
ROW_H, TOP = 6, 7  # 3x5 font, 8 characters a row; the row being sung sits at y=7, one sung row above it


def parse(lrc: str) -> list[tuple[float, str]]:
    """LRC text -> [(seconds, line)] sorted. A line may carry several stamps; [ar:..] tags are skipped."""
    out = []
    for raw in lrc.splitlines():
        text = re.sub(r"\[[^\]]*\]", "", raw).strip()
        out += [(int(m) * 60 + float(s), text) for m, s in STAMP.findall(raw)]
    return sorted(out)


def _get(path: str, **q) -> object:
    req = urllib.request.Request(LRCLIB + path + "?" + urllib.parse.urlencode(q), headers=UA)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=10).read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def fetch(title: str, artist: str, album: str = "", duration: float | None = None) -> list[tuple[float, str]]:
    """Synced lyrics, or [] when LRCLIB has none (or only plain, unsynced ones). Network errors raise."""
    q = {"track_name": title, "artist_name": artist, "album_name": album}
    if duration:
        q["duration"] = round(duration)
    hit = _get("get", **q)
    if hit and hit.get("syncedLyrics"):
        return parse(hit["syncedLyrics"])
    for h in _get("search", track_name=NOISE.sub("", title), artist_name=artist) or []:
        if h.get("syncedLyrics") and (not duration or abs((h.get("duration") or 0) - duration) < 5):
            return parse(h["syncedLyrics"])
    return []


def _dim(c, f: float) -> tuple:
    return tuple(int(v * f) for v in c)


def _ease(f: float) -> float:
    """Hold a row still while it's sung, then glide up to the next one in the last quarter."""
    f = max(0.0, (f - 0.75) / 0.25)
    return f * f * (3 - 2 * f)


def frame(lines: list | None, pos: float | None, title: str = "") -> Image.Image:
    """Karaoke: each line in its own colour fills in letter by letter as it's sung (unsung letters white),
    upcoming lines in a dim tint, and the text glides up a row at a time. lines None = still looking."""
    img = render.blank()
    if not lines or pos is None:
        msg = "LYRICS..." if lines is None else "NO SYNCED LYRICS"
        for n, r in enumerate((render.wrap(render.clean(title), 8)[:2] + [""] + render.wrap(msg, 8))[:5]):
            render.draw_text(img, 1, 1 + n * ROW_H, r, PALETTE[0] if n < 2 else render.DIM)
        return img
    i = bisect.bisect_right([t for t, _ in lines], pos) - 1
    wrapped = [render.wrap(render.clean(text), 8) for _, text in lines]
    starts = [0]
    for w in wrapped:
        starts.append(starts[-1] + len(w))
    p = 0.0
    if i >= 0:
        dur = (lines[i + 1][0] if i + 1 < len(lines) else lines[i][0] + 8) - lines[i][0]
        letters = sum(len(r.replace(" ", "")) for r in wrapped[i])
        # ponytail: lines have no word timing; fill at ~4 letters/s, done by the next line. Word-synced LRC would be exact.
        p = min(1.0, (pos - lines[i][0]) / max(0.3, min(dur * 0.9, letters * 0.25 + 1.0)))
    anchor = starts[i] + p * len(wrapped[i]) if i >= 0 else 0.0
    scroll = int(anchor) + _ease(anchor - int(anchor))
    first = max(0, int(scroll) - 2)
    for li in range(max(0, bisect.bisect_right(starts, first) - 1), len(lines)):
        if starts[li] > scroll + 5:
            break
        hue, sung = PALETTE[li % len(PALETTE)], 0
        lit = sum(len(r.replace(" ", "")) for r in wrapped[li]) * p if li == i else 0
        for k, row in enumerate(wrapped[li]):
            y = TOP + round((starts[li] + k - scroll) * ROW_H)
            for j, ch in enumerate(row):
                if li < i:
                    c = _dim(hue, 0.3)
                elif li > i:
                    c = _dim(hue, 0.45)
                else:
                    c = hue if sung < int(lit) else WHITE
                if ch != " ":
                    render.draw_text(img, 1 + 4 * j, y, ch, c)
                    sung += 1
    return img


if __name__ == "__main__":
    ls = parse("[ar:Someone]\n[00:01.00]first line here\n[00:04.50][00:20.00]chorus\n[00:08]\n"
               "[00:10.00]a much longer line that will not fit on one small panel at all\n[00:15.00]end")
    assert ls[0] == (1.0, "first line here") and ls[1] == (4.5, "chorus") and ls[-1] == (20.0, "chorus")
    assert ls[2] == (8.0, "")  # an instrumental gap is a blank line
    colours = lambda img, y0, y1: {img.getpixel((x, y)) for x in range(32) for y in range(max(0, y0), y1)} - {(0, 0, 0)}
    a = frame(ls, 0.5)  # before the first line: only dim tints, first line at the singing row
    assert WHITE not in colours(a, 0, 32) and colours(a, 7, 12) == {_dim(PALETTE[0], 0.45)}
    b = frame(ls, 1.05)  # FIRST / LINE / HERE just started: white, nothing filled yet
    assert colours(b, 7, 12) == {WHITE}
    c = frame(ls, 2.5)  # partway: first letters in the line's colour, the rest still white
    assert colours(c, 0, 32) >= {WHITE, PALETTE[0]}
    d = frame(ls, 4.4)  # filled, glided up: line 1 fully coloured, CHORUS next in its dim tint
    assert WHITE not in colours(d, 0, 32) and _dim(PALETTE[1], 0.45) in colours(d, 0, 32)
    e = frame(ls, 4.55)  # chorus just started at the anchor row; the sung line above is dimmed
    assert colours(e, 7, 12) == {WHITE} and _dim(PALETTE[0], 0.3) in colours(e, 0, 7)
    frames = {frame(ls, 10 + t / 2).tobytes() for t in range(10)}
    assert len(frames) > 5  # the long line fills and scrolls instead of jumping a page
    assert PALETTE[0] in colours(frame(None, None, "Song"), 0, 12) and frame([], 3.0, "Song").getbbox()
    assert frame([(0.0, "ஒரு நாள்")], 0.1).getbbox()  # Tamil is romanised, not dropped
    assert NOISE.sub("", "Song - Remastered 2011") == "Song" and NOISE.sub("", "Song (feat. X)") == "Song"
    print("lyrics ok")
