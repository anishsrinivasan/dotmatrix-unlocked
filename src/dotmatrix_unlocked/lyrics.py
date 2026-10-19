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
NOW, NEXT = (255, 255, 255), render.DIM
ROWS, ROW_H = 5, 6  # 3x5 font, 8 characters a row


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


def frame(lines: list | None, pos: float | None, title: str = "") -> Image.Image:
    """lines None = still looking. The current line in white, wrapped; what comes next dimmed below it.
    A line longer than the panel pages through while it's being sung."""
    img = render.blank()
    if not lines or pos is None:
        msg = "LYRICS..." if lines is None else "NO SYNCED LYRICS"
        rows = render.wrap(msg, 8) + [""] + render.wrap(render.clean(title), 8)
        for i, r in enumerate(rows[:ROWS]):
            render.draw_text(img, 1, 1 + i * ROW_H, r, NOW if i < 2 and lines is None else NEXT)
        return img
    i = bisect.bisect_right([t for t, _ in lines], pos) - 1
    now = render.wrap(render.clean(lines[i][1]), 8) if i >= 0 else []
    if len(now) > ROWS:  # page through it over the line's time on screen
        start, end = lines[i][0], lines[i + 1][0] if i + 1 < len(lines) else lines[i][0] + 8
        page = min(int((pos - start) / max(end - start, 0.1) * -(-len(now) // ROWS)), -(-len(now) // ROWS) - 1)
        now = now[page * ROWS:(page + 1) * ROWS]
    rows = [(r, NOW) for r in now]
    for _, text in lines[i + 1:]:
        if len(rows) >= ROWS:
            break
        rows += [(r, NEXT) for r in render.wrap(render.clean(text), 8)]
    for n, (r, c) in enumerate(rows[:ROWS]):
        render.draw_text(img, 1, 1 + n * ROW_H, r, c)
    return img


if __name__ == "__main__":
    ls = parse("[ar:Someone]\n[00:01.00]first line here\n[00:04.50][00:20.00]chorus\n[00:08]\n"
               "[00:10.00]a much longer line that will not fit on one small panel at all\n[00:15.00]end")
    assert ls[0] == (1.0, "first line here") and ls[1] == (4.5, "chorus") and ls[-1] == (20.0, "chorus")
    assert ls[2] == (8.0, "")  # an instrumental gap is a blank line
    lit = lambda img, y0, y1, c: any(img.getpixel((x, y)) == c for x in range(32) for y in range(y0, y1))
    a = frame(ls, 0.5)  # before the first line: nothing white, upcoming lines dim
    assert not lit(a, 0, 32, NOW) and lit(a, 0, 6, NEXT)
    b = frame(ls, 2.0)  # FIRST / LINE / HERE in white, then CHORUS dimmed
    assert lit(b, 13, 18, NOW) and not lit(b, 19, 24, NOW) and lit(b, 19, 24, NEXT)
    assert frame(ls, 2.0).tobytes() != frame(ls, 5.0).tobytes()
    assert frame(ls, 10.5).tobytes() != frame(ls, 14.5).tobytes()  # long line pages through
    assert lit(frame(None, None, "Song"), 0, 12, NOW) and lit(frame([], 3.0, "Song"), 0, 32, NEXT)
    assert NOISE.sub("", "Song - Remastered 2011") == "Song" and NOISE.sub("", "Song (feat. X)") == "Song"
    print("lyrics ok")
