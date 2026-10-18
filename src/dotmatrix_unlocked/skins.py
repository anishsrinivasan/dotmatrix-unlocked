"""Skins that aren't the dashboard: album art, vinyl (GIF), user GIFs."""
import colorsys
import io
import math

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageSequence

MAX_FRAMES = 48
MIN_DELAY_MS = 40


def album(art: Image.Image) -> Image.Image:
    return ImageOps.fit(art.convert("RGB"), (32, 32), Image.LANCZOS)


def vinyl_frames(art: Image.Image | None, n: int = 12) -> list[Image.Image]:
    """Spinning record: grooves + a rotating glint, album art on the label, static tonearm.
    Drawn at 4x then downsampled so the rotation reads smoothly at 32px."""
    S = 128
    label = None
    if art is not None:
        label = ImageOps.fit(art.convert("RGB"), (52, 52), Image.LANCZOS)
        mask = Image.new("L", label.size)
        ImageDraw.Draw(mask).ellipse((0, 0, 51, 51), fill=255)
    frames = []
    for i in range(n):
        a = 360 * i / n
        im = Image.new("RGB", (S, S))
        d = ImageDraw.Draw(im)
        d.ellipse((4, 4, 123, 123), fill=(22, 22, 26))
        for r in (54, 46, 38):
            d.ellipse((64 - r, 64 - r, 64 + r, 64 + r), outline=(40, 40, 46), width=2)
        for off in (0, 180):  # two opposite glints
            rad = math.radians(a + off)
            for t in range(30, 60, 2):
                x, y = 64 + t * math.cos(rad), 64 + t * math.sin(rad)
                d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(95, 95, 110))
        if label is not None:
            im.paste(label.rotate(-a), (38, 38), mask)
        else:
            d.ellipse((38, 38, 89, 89), fill=(217, 119, 87))
            rad = math.radians(a)
            d.ellipse((64 + 16 * math.cos(rad) - 4, 64 + 16 * math.sin(rad) - 4,
                       64 + 16 * math.cos(rad) + 4, 64 + 16 * math.sin(rad) + 4), fill=(255, 220, 190))
        d.ellipse((61, 61, 67, 67), fill=(0, 0, 0))
        d.line((120, 6, 110, 40, 90, 58), fill=(170, 170, 180), width=5)  # tonearm
        frames.append(im.resize((32, 32), Image.LANCZOS))
    return frames


def to_gif(frames: list[Image.Image], delays: list[int] | int, colors: int = 256) -> bytes:
    """One palette shared by every frame, no dithering: dither speckle is loud on 32x32 LEDs, and per-frame
    palettes make flat areas flicker."""
    delays = [delays] * len(frames) if isinstance(delays, int) else delays
    w, h = frames[0].size
    sheet = Image.new("RGB", (w * len(frames), h))
    for i, f in enumerate(frames):
        sheet.paste(f.convert("RGB"), (w * i, 0))
    pal = sheet.quantize(colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out = [f.convert("RGB").quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    buf = io.BytesIO()
    out[0].save(buf, format="GIF", save_all=True, append_images=out[1:], duration=delays,
                loop=0, disposal=1, optimize=False)
    return buf.getvalue()


def _shrink(img: Image.Image, pixel_art: bool) -> Image.Image:
    """Center-crop to square, then to 32x32. Pixel art keeps hard edges (nearest); everything else is
    area-averaged via 64px with a light sharpen, so detail survives instead of turning to mush."""
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side))
    if pixel_art:
        return img.resize((32, 32), Image.NEAREST)
    img = img.resize((64, 64), Image.BOX).filter(ImageFilter.UnsharpMask(radius=1, percent=70, threshold=2))
    return ImageEnhance.Color(img.resize((32, 32), Image.BOX)).enhance(1.3)  # averaging drains colour; give it back


def _levels(frames: list[Image.Image], cut: float = 0.01) -> list[Image.Image]:
    """Stretch contrast using the whole clip's histogram (per-frame would flicker)."""
    hist = [0] * 256
    for f in frames:
        hist = [a + b for a, b in zip(hist, f.convert("L").histogram())]
    n, acc, lo = sum(hist), 0, 0
    for lo, c in enumerate(hist):
        acc += c
        if acc > n * cut:
            break
    acc, hi = 0, 255
    for hi in range(255, -1, -1):
        acc += hist[hi]
        if acc > n * cut:
            break
    hi = max(hi, lo + 48)  # don't blow up nearly-flat clips
    lut = [max(0, min(255, round((v - lo) * 255 / (hi - lo)))) for v in range(256)] * 3
    return [f.point(lut) for f in frames]


def normalize_gif(data: bytes) -> list[tuple[Image.Image, int]]:
    """Any image/GIF -> list of (32x32 RGB frame, delay ms), <= MAX_FRAMES, tuned for LEDs."""
    src = Image.open(io.BytesIO(data))
    frames = []
    for f in ImageSequence.Iterator(src):
        rgba = f.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        frames.append((Image.alpha_composite(bg, rgba).convert("RGB"), max(MIN_DELAY_MS, f.info.get("duration", 100))))
    if len(frames) > MAX_FRAMES:  # keep total runtime: sample evenly, stretch delays
        step = len(frames) / MAX_FRAMES
        total = sum(d for _, d in frames)
        frames = [(frames[int(i * step)][0], max(MIN_DELAY_MS, total // MAX_FRAMES)) for i in range(MAX_FRAMES)]
    first = frames[0][0]
    colors = first.getcolors(64)
    pixel_art = min(first.size) <= 64 or colors is not None  # tiny or few flat colours: keep it crisp
    imgs = _levels([_shrink(f, pixel_art) for f, _ in frames]) if not pixel_art else [_shrink(f, True) for f, _ in frames]
    return list(zip(imgs, [d for _, d in frames]))


MAX_GIF_BYTES = 40_000  # ponytail: panel's real limit unknown; 13KB and 75KB both acked, 40KB keeps uploads ~5s


def fit(frames: list[tuple[Image.Image, int]]) -> bytes:
    """Encode under MAX_GIF_BYTES: first fewer colours (barely visible at 32px), only then drop frames."""
    while True:
        for colors in (256, 128, 64, 32):
            data = to_gif([f for f, _ in frames], [d for _, d in frames], colors)
            if len(data) <= MAX_GIF_BYTES:
                return data
        if len(frames) <= 2:
            return data
        frames = [(f, d * 2) for f, d in frames[::2]]


def video_idle() -> Image.Image:
    """Video skin with nothing loaded: a play button."""
    from . import render
    img = render.blank()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 5, 25, 20), 3, fill=(200, 40, 40))
    d.polygon([(13, 9), (13, 16), (19, 12)], fill=(255, 255, 255))
    render.draw_text(img, 6, 24, "VIDEO", render.DIM)
    return img


def nothing_playing() -> Image.Image:
    from . import render
    img = render.blank()
    for x, y in [(14, 6), (15, 6), (16, 6), (17, 6), (17, 7), (17, 8), (17, 9), (17, 10), (17, 11), (14, 7),
                 (14, 8), (14, 9), (14, 10), (14, 11), (12, 11), (13, 11), (12, 12), (13, 12), (15, 11), (16, 11),
                 (15, 12), (16, 12)]:
        img.putpixel((x, y), (30, 215, 96))
    render.draw_text(img, 2, 18, "NOTHING", render.DIM)
    render.draw_text(img, 4, 24, "PLAYING", render.DIM)
    return img


def _heat(f: float) -> tuple:  # Winamp meter colors by height, 0..1
    return (40, 220, 60) if f < 0.5 else (230, 210, 30) if f < 0.8 else (240, 50, 40)


def _hue(f: float, v: float = 1.0) -> tuple:
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(f % 1, 1, v))


class Visualizer:
    """Music visualizer styles over 16 smoothed bands (fast attack, slow fall, peak caps that hang then drop).
    ponytail: driven by a synthetic beat (~120bpm kick + noisy mids/highs) since macOS gives no system-audio
    levels without a loopback device; feed real band levels into bands() later (mic or BlackHole + FFT).
    To add a style: write _style_<name>(px) and add it to STYLES."""
    FPS, N = 12, 16
    STYLES = {"bars": "Winamp bars", "spectrum": "Rainbow spectrum", "mirror": "Mirror", "scope": "Oscilloscope",
              "radial": "Radial burst", "rings": "Beat rings", "vu": "VU meters"}

    def __init__(self, seed=0):
        import random
        self.rnd = random.Random(seed)
        self.level, self.peak, self.hold = [0.0] * self.N, [0.0] * self.N, [0] * self.N
        self.beat, self.rings, self.last, self.t = 0.0, [], None, 0.0

    def bands(self, t: float) -> list[float]:
        beat = max(0.0, 1 - (t * 2 % 1) * 3)  # kick every 0.5s, ~0.17s decay
        out = []
        for i in range(self.N):
            f = i / (self.N - 1)
            base = 0.75 - 0.4 * f + 0.25 * math.sin(t * (1.3 + i * 0.35) + i)
            out.append(max(0.0, min(1.0, base * (0.55 + 0.45 * self.rnd.random()) + beat * (1 - f) * 0.5)))
        return out

    def _advance(self, t: float, playing: bool, real: list[float] | None = None) -> None:
        playing = playing or real is not None
        target = real if real is not None else self.bands(t) if playing else [0.0] * self.N
        for i, v in enumerate(target):
            self.level[i] = v if v > self.level[i] else self.level[i] * 0.65
            if self.level[i] >= self.peak[i]:
                self.peak[i], self.hold[i] = self.level[i], 4
            elif self.hold[i]:
                self.hold[i] -= 1
            else:
                self.peak[i] = max(0.0, self.peak[i] - 0.06)
        bass = sum(self.level[:3]) / 3
        if playing and bass > 0.7 and bass > self.beat + 0.1:  # onset -> new ring
            self.rings.append(0.0)
        self.beat = bass
        self.rings = [r + 1.6 for r in self.rings if r < 24]
        self.t = t if playing else self.t  # scope phase freezes when paused

    def frame(self, t: float, playing: bool, style: str = "bars", real: list[float] | None = None) -> Image.Image:
        """real: 16 band levels 0..1 from the microphone; None = synthetic beat while playing."""
        step = int(t * self.FPS)
        if step != self.last:  # advance once per tick, however often we're asked
            self.last = step
            self._advance(step / self.FPS, playing, real)
        img = Image.new("RGB", (32, 32))
        getattr(self, "_style_" + (style if style in self.STYLES else "bars"))(img.load())
        return img

    def _style_bars(self, px):  # 8 chunky bars, pairs of bands
        for i in range(8):
            lv, pk = max(self.level[2 * i:2 * i + 2]), max(self.peak[2 * i:2 * i + 2])
            for y in range(round(lv * 30)):
                for dx in range(3):
                    px[i * 4 + dx, 31 - y] = _heat(y / 30)
            if pk > 0.02:
                for dx in range(3):
                    px[i * 4 + dx, 31 - min(31, round(pk * 30) + 1)] = (200, 200, 210)

    def _style_spectrum(self, px):  # 16 thin rainbow bars
        for i in range(self.N):
            c = _hue(i / self.N * 0.85)
            for y in range(round(self.level[i] * 30)):
                px[i * 2, 31 - y] = c
            if self.peak[i] > 0.02:
                px[i * 2, 31 - min(31, round(self.peak[i] * 30) + 1)] = (255, 255, 255)

    def _style_mirror(self, px):  # bars growing up and down from the middle, bass in the center
        for i in range(self.N):
            h = round(self.level[i] * 15)
            x = 15 - i // 2 * 2 if i % 2 == 0 else 16 + i // 2 * 2  # alternate sides so bass sits mid-screen
            for y in range(h + 1):
                c = _hue(0.5 + y / 40, 0.75 + 0.25 * y / 15)
                for yy in (15 - y, 16 + y):
                    if 0 <= yy < 32 and 0 <= x < 32:
                        px[x, yy] = c

    def _style_scope(self, px):  # Winamp oscilloscope line
        amp = (sum(self.level[:4]) / 4) * 13
        prev = None
        for x in range(32):
            y = 16 + amp * (0.6 * math.sin(x / 2.2 + self.t * 9) + 0.4 * math.sin(x / 0.9 - self.t * 13) *
                            (sum(self.level[8:]) / 8))
            y = max(0, min(31, round(y)))
            for yy in range(min(y, prev), max(y, prev) + 1) if prev is not None else (y,):
                px[x, yy] = (255, 210, 60)
            prev = y

    def _style_radial(self, px):  # spokes around a circle, length = level
        for k in range(32):
            band = k if k < 16 else 31 - k
            ang = 2 * math.pi * k / 32 - math.pi / 2
            length = 3 + self.level[band] * 12
            c = _hue(k / 32)
            r = 3.0
            while r <= length:
                x, y = round(15.5 + r * math.cos(ang)), round(15.5 + r * math.sin(ang))
                if 0 <= x < 32 and 0 <= y < 32:
                    px[x, y] = c
                r += 0.5

    def _style_rings(self, px):  # bass-pulsing core, a ring flies out on every kick
        core = 1.5 + self.beat * 4
        for r in self.rings:
            fade = max(0.15, 1 - r / 24)
            c = tuple(int(v * fade) for v in _hue(0.08 + r / 40))
            for a in range(0, 360, 4):
                x, y = round(15.5 + r * math.cos(math.radians(a))), round(15.5 + r * math.sin(math.radians(a)))
                if 0 <= x < 32 and 0 <= y < 32:
                    px[x, y] = c
        for x in range(32):
            for y in range(32):
                if (x - 15.5) ** 2 + (y - 15.5) ** 2 <= core * core:
                    px[x, y] = (255, 140, 40)

    def _style_vu(self, px):  # two horizontal L/R meters, segmented, with peak ticks
        from . import render
        for row, (lv, pk) in enumerate(((sum(self.level[:8]) / 8, max(self.peak[:8])),
                                        (sum(self.level[8:]) / 8 * 1.3, max(self.peak[8:])))):
            y0 = 7 + row * 12
            render.draw_text(_Px(px), 0, y0, "LR"[row], (110, 110, 125))
            n = min(9, round(lv * 9))
            for seg in range(9):
                c = _heat(seg / 9) if seg < n else (25, 25, 32)
                for dx in range(2):
                    for dy in range(5):
                        px[5 + seg * 3 + dx, y0 + dy] = c
            p = min(8, round(min(1.0, pk) * 9))
            if pk > 0.05:
                for dy in range(5):
                    px[5 + p * 3 + 2, y0 + dy] = (220, 220, 230)


class _Px:
    """Lets render.draw_text write into a pixel-access object."""
    def __init__(self, px):
        self.px = px

    def load(self):
        return self.px


# Built-in 32x32 animations: crisp at native resolution, no account needed.
def _fire(n=24):
    import random
    rnd, h = random.Random(1), [[0.0] * 32 for _ in range(34)]
    out = []
    for i in range(n + 20):
        for x in range(32):
            h[33][x] = rnd.random() ** 0.5
        for y in range(33):
            for x in range(32):
                h[y][x] = (h[y + 1][(x - 1) % 32] + h[y + 1][x] + h[y + 1][(x + 1) % 32] + h[min(33, y + 2)][x]) / 4.12
        if i >= 20:
            im = Image.new("RGB", (32, 32))
            for y in range(32):
                for x in range(32):
                    v = h[y + 1][x]
                    im.putpixel((x, y), (min(255, int(v * 700)), min(255, int(v * 300)), min(255, int(v * 80))))
            out.append((im, 70))
    return out


def _matrix(n=32):
    import random
    rnd = random.Random(2)
    drops = [(rnd.randrange(32), rnd.randrange(32), rnd.choice((1, 1, 2))) for _ in range(14)]
    out = []
    for i in range(n):
        im = Image.new("RGB", (32, 32))
        for x, y0, sp in drops:
            head = (y0 + i * sp) % 32
            for k in range(10):
                y = head - k
                if 0 <= y < 32:
                    g = 255 if k == 0 else max(0, 200 - k * 22)
                    im.putpixel((x, y), (180, 255, 180) if k == 0 else (0, g, 40))
        out.append((im, 80))
    return out


def _plasma(n=24):
    out = []
    for i in range(n):
        t = 2 * math.pi * i / n
        im = Image.new("RGB", (32, 32))
        for y in range(32):
            for x in range(32):
                v = math.sin(x / 5 + t) + math.sin(y / 4 - t) + math.sin((x + y) / 7 + t) + math.sin(math.hypot(x - 16, y - 16) / 4 - t)
                im.putpixel((x, y), tuple(int(127 + 127 * math.sin(v * math.pi / 2 + o)) for o in (0, 2.1, 4.2)))
        out.append((im, 80))
    return out


def _starfield(n=30):
    import random
    rnd = random.Random(3)
    stars = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(0.1, 1)) for _ in range(60)]
    out = []
    for i in range(n):
        im = Image.new("RGB", (32, 32))
        for sx, sy, z0 in stars:
            z = (z0 - i / n) % 1 or 1
            x, y = int(16 + sx * 8 / z), int(16 + sy * 8 / z)
            if 0 <= x < 32 and 0 <= y < 32:
                b = int(255 * (1 - z))
                im.putpixel((x, y), (b, b, min(255, b + 40)))
        out.append((im, 60))
    return out


def _heart(n=12):
    out = []
    for i in range(n):
        s = 1 + 0.18 * max(0, math.sin(2 * math.pi * i / n * 2)) * (i < n // 2)
        im = Image.new("RGB", (32, 32))
        for y in range(32):
            for x in range(32):
                u, v = (x - 15.5) / (11 * s), -(y - 14) / (11 * s)
                if (u * u + v * v - 1) ** 3 - u * u * v ** 3 <= 0:
                    im.putpixel((x, y), (230, 30, 60))
        out.append((im, 90))
    return out


def _life(n=40):
    import random
    rnd = random.Random(4)
    g = {(x, y) for x in range(32) for y in range(32) if rnd.random() < 0.3}
    out = []
    for i in range(n):
        im = Image.new("RGB", (32, 32))
        for x, y in g:
            im.putpixel((x, y), (60 + x * 6, 120, 255 - y * 6))
        out.append((im, 150))
        cnt = {}
        for x, y in g:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        k = ((x + dx) % 32, (y + dy) % 32)
                        cnt[k] = cnt.get(k, 0) + 1
        g = {k for k, c in cnt.items() if c == 3 or (c == 2 and k in g)}
    return out


def _px(im, x, y, c):
    if 0 <= x < 32 and 0 <= y < 32:
        im.putpixel((int(x), int(y)), c)


def _rain(n=16):
    import random
    rnd = random.Random(5)
    drops = [(rnd.randrange(32), rnd.randrange(32), rnd.choice((2, 2, 4))) for _ in range(26)]
    out = []
    for i in range(n):
        im = Image.new("RGB", (32, 32), (4, 6, 16))
        for x in range(32):
            _px(im, x, 31, (20, 30, 60))
        for x, y0, sp in drops:  # period: 32 rows / speed divides n*speed evenly -> seamless loop
            y = (y0 + i * sp) % 32
            for k in range(3):
                _px(im, x, y - k, (90 - k * 25, 140 - k * 35, 255 - k * 60))
            if y >= 29:  # splash
                _px(im, x - 1, 30, (120, 170, 255)); _px(im, x + 1, 30, (120, 170, 255))
        out.append((im, 70))
    return out


def _snow(n=32):
    import random
    rnd = random.Random(6)
    flakes = [(rnd.uniform(0, 32), rnd.randrange(32), rnd.choice((1, 1, 2)), rnd.uniform(0, 6.28)) for _ in range(40)]
    out = []
    for i in range(n):
        im = Image.new("RGB", (32, 32), (6, 8, 22))
        for x in range(32):
            for y in (30, 31):
                _px(im, x, y, (200, 210, 230) if y == 31 or (x * 7) % 5 else (150, 160, 190))
        for x, y0, sp, ph in flakes:
            y = (y0 + i * sp) % 32
            sx = x + 1.2 * math.sin(2 * math.pi * i / n * 2 + ph)
            _px(im, round(sx) % 32, y, (255, 255, 255) if sp == 2 else (170, 180, 210))
        out.append((im, 110))
    return out


def _fireworks(n=36):
    import random
    rnd = random.Random(7)
    shows = [(rnd.randrange(6, 26), rnd.randrange(5, 14), k * n // 3, rnd.random()) for k in range(3)]
    out = []
    for i in range(n):
        im = Image.new("RGB", (32, 32), (2, 2, 10))
        for cx, cy, start, hue in shows:
            t = (i - start) % n
            if t < 6:  # rocket climbing
                _px(im, cx, 31 - (31 - cy) * t / 6, (255, 220, 160))
            elif t < 20:  # burst: a flash, then sparks flying out, falling and fading, with short trails
                k = t - 6
                fade = max(0.0, 1 - k / 14) ** 0.8
                base = colorsys.hsv_to_rgb(hue, 0.75, 1)
                if k == 0:
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            _px(im, cx + dx, cy + dy, (255, 255, 230))
                for j in range(18):
                    a = 2 * math.pi * j / 18
                    for tail, dim in ((0, 1.0), (1.2, 0.45)):
                        r = max(0.0, k * 1.4 - tail)
                        c = tuple(int(v * 255 * fade * dim) for v in base)
                        _px(im, round(cx + r * math.cos(a)), round(cy + r * math.sin(a) + k * k * 0.04), c)
        out.append((im, 80))
    return out


def _aquarium(n=24):
    out = []
    for i in range(n):
        im = Image.new("RGB", (32, 32))
        for y in range(32):
            for x in range(32):
                im.putpixel((x, y), (0, 20 + y * 2, 60 + y * 3))
        for x in range(32):
            _px(im, x, 31, (190, 170, 110)); _px(im, x, 30, (160, 140, 90) if x % 3 else (190, 170, 110))
        for base in (4, 26):  # swaying weed
            for y in range(20, 30):
                _px(im, base + round(math.sin(2 * math.pi * i / n + y / 3)), y, (30, 160, 70))
        for k, (y, speed, col) in enumerate(((9, 1, (255, 140, 40)), (17, -1, (250, 220, 60)), (24, 2, (240, 90, 140)))):
            fx = (k * 11 + i * speed * 32 // n) % 44 - 6  # whole tank width per loop
            d = 1 if speed > 0 else -1
            for dx, dy in ((0, 0), (1, 0), (2, 0), (3, 0), (1, -1), (2, -1), (1, 1), (2, 1)):
                _px(im, fx + dx * d, y + dy, col)
            _px(im, fx - d, y - 1, col); _px(im, fx - d, y + 1, col)  # tail
            _px(im, fx + 3 * d, y - 1, (0, 0, 0))  # eye
        for k in range(3):  # bubbles
            by = 28 - ((i * 2 + k * 9) % 28)
            _px(im, 6 + k * 9 + round(math.sin(by / 3)), by, (170, 220, 255))
        out.append((im, 90))
    return out


def _pacman(n=24):
    out = []
    for i in range(n):
        im = Image.new("RGB", (32, 32))
        x = -6 + i * 46 // n
        for d in range(3, 32, 5):
            if d > x + 3:
                _px(im, d, 16, (255, 200, 170)); _px(im, d + 1, 16, (255, 200, 170))
        mouth = abs((i % 4) - 2) * 0.35
        for yy in range(-5, 6):
            for xx in range(-5, 6):
                ang = math.atan2(yy, xx)
                if xx * xx + yy * yy <= 25 and not (abs(ang) < mouth and xx > 0):
                    _px(im, x + xx, 16 + yy, (255, 220, 0))
        gx = x - 14
        for yy in range(-5, 6):
            for xx in range(-5, 6):
                if (yy < 0 and xx * xx + yy * yy <= 25) or (yy >= 0 and abs(xx) <= 5 and not (yy == 5 and (xx + i) % 2)):
                    _px(im, gx + xx, 16 + yy, (255, 80, 80))
        for ex in (-2, 2):
            _px(im, gx + ex, 14, (255, 255, 255)); _px(im, gx + ex + 1, 14, (40, 60, 255))
        out.append((im, 70))
    return out


INVADER = ["..#.....#..", "...#...#...", "..#######..", ".##.###.##.", "###########", "#.#######.#", "#.#.....#.#",
           "...##.##..."]
INVADER2 = ["..#.....#..", "#..#...#..#", "#.#######.#", "###.###.###", "###########", ".#########.", "..#.....#..",
            ".#.......#."]


def _invaders(n=16):
    out = []
    for i in range(n):
        im = Image.new("RGB", (32, 32))
        ox = round(3 * math.sin(2 * math.pi * i / n))
        sprite = INVADER if i % 4 < 2 else INVADER2
        for row, (y0, col) in enumerate(((2, (80, 255, 120)), (12, (255, 90, 200)))):
            for k in range(2):
                for r, line in enumerate(sprite):
                    for c, ch in enumerate(line):
                        if ch == "#":
                            _px(im, 4 + ox + k * 13 + c, y0 + r, col)
        shipx = 15 + round(8 * math.sin(2 * math.pi * i / n + 1))
        for dx in range(-2, 3):
            _px(im, shipx + dx, 30, (80, 200, 255))
        _px(im, shipx, 29, (80, 200, 255))
        shot = 28 - (i % 8) * 3
        _px(im, shipx, shot, (255, 255, 255)); _px(im, shipx, shot - 1, (255, 255, 255))
        out.append((im, 90))
    return out


def _lava(n=24):
    out = []
    blobs = [(10, 0.0, 6), (22, 0.33, 5), (15, 0.66, 7)]
    for i in range(n):
        im = Image.new("RGB", (32, 32))
        t = i / n
        centers = [(x + 2 * math.sin(2 * math.pi * (t + p) * 2), 16 + 13 * math.sin(2 * math.pi * (t + p)), r)
                   for x, p, r in blobs]
        for y in range(32):
            for x in range(32):
                v = sum(r * r / ((x - cx) ** 2 + (y - cy) ** 2 + 1) for cx, cy, r in centers)
                if v > 1.0:
                    k = min(1.0, (v - 1) / 2)
                    im.putpixel((x, y), (255, int(90 + 120 * k), int(30 * k)))
                else:
                    im.putpixel((x, y), (int(60 * v), 10, int(70 + 40 * v)))
        out.append((im, 90))
    return out


def _dvd(n=56):
    from . import render
    out = []
    w, h = 13, 7
    x, y, dx, dy, hue = 3, 5, 1, 1, 0.0
    for i in range(n):
        im = Image.new("RGB", (32, 32))
        c = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(hue, 0.8, 1))
        for xx in range(w):
            for yy in range(h):
                if (xx, yy) in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
                    continue
                im.putpixel((x + xx, y + yy), c)
        render.draw_text(im, x + 1, y + 1, "DVD", (0, 0, 0), font="regular")
        out.append((im, 80))
        nx, ny = x + dx, y + dy
        if not 0 <= nx <= 32 - w:
            dx, hue = -dx, hue + 0.23
        if not 0 <= ny <= 32 - h:
            dy, hue = -dy, hue + 0.23
        x, y = x + dx, y + dy
    return out


def _ripple(n=20):
    drops = [(10, 12, 0), (22, 20, n // 2)]
    out = []
    for i in range(n):
        im = Image.new("RGB", (32, 32))
        for y in range(32):
            for x in range(32):
                v = 0.0
                for cx, cy, st in drops:
                    r = ((i - st) % n) * 1.3
                    d = math.hypot(x - cx, y - cy)
                    if abs(d - r) < 1.2:
                        v += (1 - abs(d - r) / 1.2) * max(0.0, 1 - r / 26)
                v = min(1.0, v)
                im.putpixel((x, y), (int(10 + 120 * v), int(40 + 200 * v), int(90 + 165 * v)))
        out.append((im, 80))
    return out


def _rainbow(n=24):
    out = []
    for i in range(n):
        im = Image.new("RGB", (32, 32))
        for x in range(32):
            y0 = 16 + 9 * math.sin(2 * math.pi * (x / 32 + i / n))
            for k in range(6):
                c = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(k / 6, 1, 1))
                _px(im, x, round(y0) - 6 + k * 2, c)
                _px(im, x, round(y0) - 5 + k * 2, c)
        for k in range(8):  # twinkling stars
            if (i + k * 3) % 6 < 3:
                _px(im, (k * 13) % 32, (k * 7) % 9, (255, 255, 200))
        out.append((im, 70))
    return out


PRESETS = {"fire": _fire, "matrix": _matrix, "plasma": _plasma, "starfield": _starfield, "heart": _heart, "life": _life,
           "rain": _rain, "snow": _snow, "fireworks": _fireworks, "aquarium": _aquarium, "pacman": _pacman,
           "invaders": _invaders, "lava": _lava, "dvd": _dvd, "ripple": _ripple, "rainbow": _rainbow}


if __name__ == "__main__":
    fr = vinyl_frames(None)
    assert len(fr) == 12 and fr[0].size == (32, 32) and fr[0].tobytes() != fr[3].tobytes()
    g = to_gif(fr, 120)
    back = normalize_gif(g)
    assert len(back) == 12 and back[0][0].size == (32, 32)
    big = Image.new("RGB", (200, 100), (255, 0, 0))
    assert album(big).size == (32, 32)
    many = [Image.new("RGB", (64, 64), (i * 2, 0, 0)) for i in range(100)]
    assert len(normalize_gif(to_gif(many, 20))) == MAX_FRAMES
    # photo path stretches contrast across the clip; pixel art stays nearest-neighbour crisp
    import random
    rnd = random.Random(0)
    noise = Image.new("RGB", (200, 200))
    noise.putdata([(rnd.randint(90, 110), rnd.randint(95, 115), rnd.randint(100, 120)) for _ in range(200 * 200)])
    dull = []
    for i in range(0, 40, 4):  # a dim, low-contrast "photo": noise + a slightly brighter square
        im = noise.copy()
        ImageDraw.Draw(im).rectangle((50 + i, 50, 150, 150), fill=(130, 135, 140))
        dull.append(im)
    out = normalize_gif(to_gif(dull, 50))
    lum = [p for f, _ in out for p in f.convert("L").tobytes()]
    assert max(lum) - min(lum) > 150, (min(lum), max(lum))
    checker = Image.new("RGB", (16, 16))
    for x in range(16):
        for y in range(16):
            checker.putpixel((x, y), (255, 0, 0) if (x + y) % 2 else (0, 0, 255))
    crisp = normalize_gif(to_gif([checker, checker.rotate(90)], 100))[0][0]
    assert {crisp.getpixel((x, y)) for x in range(32) for y in range(32)} <= {(255, 0, 0), (0, 0, 255)}  # no blended purple
    for name, gen in PRESETS.items():
        fr = gen()
        assert len(fr) > 2 and fr[0][0].size == (32, 32) and len({f.tobytes() for f, _ in fr}) > 1, name
        assert len(fit(fr)) <= MAX_GIF_BYTES, name
    assert nothing_playing().getbbox() and video_idle().getpixel((14, 12)) == (255, 255, 255)
    v = Visualizer()
    flat = v.frame(0, False, "bars", real=[0.0] * 15 + [1.0])
    assert flat.getpixel((29, 31)) != (0, 0, 0) and flat.getpixel((1, 31)) == (0, 0, 0)  # real levels drive bars
    for style in Visualizer.STYLES:
        v = Visualizer()
        a, b = v.frame(0.0, True, style), v.frame(0.5, True, style)
        assert a.getbbox() and a.tobytes() != b.tobytes(), style  # moves while playing
        for k in range(80):
            still = v.frame(1 + k / 12, False, style)
        assert v.frame(30, False, style).tobytes() == still.tobytes(), style  # settles when paused: no resends
    print("ok", len(g), "bytes")
