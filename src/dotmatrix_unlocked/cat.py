"""A mischievous pixel cat that lives on the panel and picks a random bit of mischief every few seconds.
frame(t) is a pure function of time within the current act, so the same t gives the same frame (no resends).
To add an act: write _act_<name>(img, u, r) (u = seconds into the act, r = per-act Random) and list it in ACTS."""
import math
import random

from PIL import Image

from . import render
FPS = 8
PAL = {"K": (45, 38, 38), "O": (245, 165, 100), "D": (220, 115, 75), "C": (238, 226, 210), "G": (180, 172, 165),
       "P": (250, 150, 140), "W": (255, 255, 255)}
# front-facing sitting cat, 13x16; eyes, tail and raised paws are drawn on top
CAT = [
    ".K.........K.",
    "KOK.......KOK",
    "KPOKKKKKKKOPK",
    "KOOOOOOOOOOOK",
    "KOOOOOOOOOOOK",
    "KOOOOOOOOOOOK",
    "KOOOOOOOOOOOK",
    "KCCCCCPCCCCCK",
    "KCCCCKCKCCCCK",
    ".KCCCCCCCCCK.",
    "..KOCCCCCOK..",
    ".KOOCCCCCOOK.",
    ".KDOCGGGCODK.",
    ".KOOCCCCCOOK.",
    ".KOKCCKCCKOK.",
    "..KKKKKKKKK..",
]
TAIL = [[(12, 13), (13, 13), (14, 12), (14, 11), (14, 10)],
        [(12, 13), (13, 12), (14, 11), (15, 10), (15, 9)]]


def _put(px, x, y, c):
    if 0 <= x < 32 and 0 <= y < 32:
        px[x, y] = c


def draw_cat(img, x, y, eyes="open", look=(0, 0), tail=0, paw=None):
    """eyes: open | closed | smug. look: (-1..1, -1..0). paw: None | 'left' | 'right' (raised)."""
    px = img.load()
    for i, (tx, ty) in enumerate(TAIL[tail % 2]):
        _put(px, x + tx, y + ty, PAL["D"] if i == len(TAIL[0]) - 1 else PAL["O"])
    for r, row in enumerate(CAT):
        for c, ch in enumerate(row):
            if ch != ".":
                _put(px, x + c, y + r, PAL[ch])
    for ex in (2, 8):  # eye sockets are 3 wide; a 2-wide eye shifts to look
        if eyes == "closed":
            for dx in range(3):
                _put(px, x + ex + dx, y + 6, PAL["K"])
        else:
            col = ex + (1 if look[0] > 0 or (look[0] == 0 and ex == 2) else 0)
            top = y + 5 + (look[1] if eyes == "open" else 1)
            for dx in (0, 1):
                for dy in ((0, 1) if eyes == "open" else (0,)):
                    _put(px, x + col + dx, top + dy, PAL["K"])
            if eyes == "open":
                _put(px, x + col + 1, top, PAL["W"])
            else:  # smug: heavy lid
                for dx in range(3):
                    _put(px, x + ex + dx, top - 1, PAL["D"])
    if paw:
        px0 = x - 2 if paw == "left" else x + 13
        for dx in (0, 1):
            for dy in (0, 1):
                _put(px, px0 + dx, y + 9 + dy, PAL["C"])
        for dx in (0, 1):
            _put(px, px0 + dx, y + 8, PAL["K"])


def _blink(u):
    return "closed" if u % 2.7 < 0.15 else "open"


# ---- acts
def _act_idle(img, u, r):
    looks = [(r.choice((-1, 0, 1)), r.choice((0, 0, -1))) for _ in range(8)]
    draw_cat(img, 9, 16, _blink(u), looks[int(u / 1.5) % 8], tail=int(u * 2))


def _act_laser(img, u, r):
    a, b = r.uniform(0.7, 1.3), r.uniform(1.1, 1.7)
    dx, dy = 15 + 13 * math.sin(u * a * 2), 8 + 6 * math.sin(u * b * 2 + 1)
    if u < 6:
        px = img.load()
        _put(px, round(dx), round(dy), (255, 30, 30))
        look = (-1 if dx < 13 else 1 if dx > 18 else 0, -1 if dy < 10 else 0)
        draw_cat(img, 9, 16, "open", look, tail=int(u * 4))
    else:  # pounce at where the dot was
        k = min(1.0, (u - 6) / 0.6)
        tx = max(0, min(19, round(dx) - 6))
        draw_cat(img, round(9 + (tx - 9) * k), round(16 - 8 * math.sin(math.pi * k)), "open", (0, -1), 1, "left")


def _act_yarn(img, u, r):
    px = img.load()
    hit = 3.0
    bx = 32 - u * 5 if u < hit else 17 + (u - hit) * 14  # rolls in, gets batted away
    for dx, dy in ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, -1), (1, 2)):
        _put(px, round(bx) + dx, 28 + dy, (230, 70, 120) if (dx + dy) % 2 else (190, 40, 90))
    if u < hit:
        _put(px, round(bx) + 3, 30, (230, 70, 120))  # trailing thread
    look = (1, 0) if bx > 13 else (0, 0)
    draw_cat(img, 2, 16, "open", look, tail=int(u * 3), paw="right" if hit - 0.4 < u < hit + 0.3 else None)


def _act_knock(img, u, r):
    px = img.load()
    for x in range(0, 15):
        _put(px, x, 13, (120, 80, 50))  # shelf
    cx, cy = 7.0, 9.0
    if u > 2.6:  # slides off the shelf, then falls
        t = u - 2.6
        cx = 7 - t * 10
        cy = 9 + (0 if cx > 0 else (t - 0.7) ** 2 * 40)
    for dx in range(3):
        for dy in range(4):
            _put(px, round(cx) + dx, round(cy) + dy, (230, 230, 240))
    _put(px, round(cx) + 3, round(cy) + 1, (230, 230, 240))  # mug handle
    _put(px, round(cx) + 1, round(cy), (120, 70, 40))  # coffee
    eyes = "smug" if u > 3.6 else "open"
    look = (0, 0) if u > 3.6 else (-1, -1)
    draw_cat(img, 17, 16, eyes, look, tail=int(u * 2), paw="left" if 2.0 < u < 2.9 else None)


def _act_sleep(img, u, r):
    breathe = int(u) % 2
    draw_cat(img, 9, 16 + breathe, "closed", tail=0)
    for k in range(2):  # two z's drifting up, half a cycle apart
        p = (u * 0.5 + k / 2) % 1
        zx, zy = 20 + round(p * 7), 14 - round(p * 14)
        c = tuple(int(v * (1 - p * 0.7)) for v in (160, 180, 255))
        render.draw_text(img, zx, zy, "Z", c, font="small")


def _act_peek(img, u, r):
    x = r.choice((2, 9, 17))
    if u < 1:
        draw_cat(img, 9, 16 + round(u * 16), "open", (0, 0))
    elif u < 2.5:
        pass
    elif u < 5:
        look = ((-1, 0), (1, 0), (0, -1))[int(u * 1.2) % 3]
        draw_cat(img, x, 25, _blink(u), look)  # ears + eyes over the bottom edge
    else:
        k = min(1.0, (u - 5) / 0.8)
        draw_cat(img, x, round(25 - 9 * k), "open", (0, 0))


def _act_zoomies(img, u, r):
    s = math.sin(u * 3.2)
    draw_cat(img, round(9 + 9 * s), round(16 - abs(math.sin(u * 6.4)) * 5), "open",
             (1 if math.cos(u * 3.2) > 0 else -1, 0), tail=int(u * 8))


# ---- moods: acts driven by what's happening on the Mac, not the random schedule
def _sprite(px, x, y, rows, c):
    for r, row in enumerate(rows):
        for cc, ch in enumerate(row):
            if ch == "#":
                _put(px, x + cc, y + r, c)


HEART = [".#.#.", "#####", "#####", ".###.", "..#.."]
NOTE = ["..##", "..#.", "..#.", "###.", "##.."]


def _act_ask(img, u, r):  # Claude needs input: wave + question bubble
    px = img.load()
    on = int(u * 2) % 2 == 0
    _sprite(px, 22, 2, [".#####.", "#######", "#######", "#######", "#######", ".#####.", "...##..", "...#..."],
            (235, 235, 240))
    render.draw_text(img, 24, 3, "?", (255, 200, 0) if on else (200, 120, 0))
    draw_cat(img, 7, 16, "open", (1, -1), tail=int(u * 4), paw="left" if on else "right")


def _act_greet(img, u, r):  # you're back: hop + hearts
    px = img.load()
    for k in range(2):
        p = (u * 0.7 + k / 2) % 1
        _sprite(px, (2, 25)[k], 12 - round(p * 12), HEART, tuple(int(v * (1 - p * 0.6)) for v in (250, 90, 130)))
    draw_cat(img, 9, round(16 - abs(math.sin(u * 5)) * 4), "open", (0, 0), tail=int(u * 6))


def _act_work(img, u, r):  # Claude working: types on a tiny laptop
    px = img.load()
    for x in range(1, 11):
        for y in range(22, 29):
            frame = x in (1, 10) or y in (22, 28)
            _put(px, x, y, (110, 110, 125) if frame else (20, 35, 60))
    for x in range(0, 12):
        _put(px, x, 29, (150, 150, 165))  # keyboard deck
    lines = int(u * 3) % 10  # code scrolling up the screen
    for i in range(min(lines, 3)):
        w = 2 + (lines + i * 3) % 6
        for x in range(w):
            _put(px, 2 + x, 24 + i * 1 + i, (90, 200, 255) if i % 2 else (217, 119, 87))
    if int(u * 2) % 2:
        _put(px, 3 + (lines % 6), 27, (255, 255, 255))  # cursor
    draw_cat(img, 15, 16, "open", (-1, 0), tail=int(u * 2), paw="left" if int(u * 6) % 2 else None)


def _act_dance(img, u, r):  # music: bob to the beat, notes float up
    px = img.load()
    beat = int(u * 2) % 2
    for k in range(2):
        p = (u * 0.5 + k / 2) % 1
        x = (2, 26)[k] + round(math.sin(p * 6) * 2)
        _sprite(px, x, 14 - round(p * 13), NOTE, tuple(int(v * (1 - p * 0.6)) for v in (30, 215, 96)))
    draw_cat(img, 9 + (1 if beat else -1), 16 + beat, "open", ((1 if beat else -1), 0), tail=int(u * 8),
             paw=("left", "right")[int(u * 2) % 2] if int(u) % 4 == 3 else None)


def _act_startle(img, u, r):  # loud noise: jumps, fur puffed out, "!"
    px = img.load()
    k = min(1.0, u / 0.25)
    y = round(16 - 7 * math.sin(math.pi * min(1.0, u / 1.2)))
    render.draw_text(img, 24, 2, "!", (255, 220, 0))
    draw_cat(img, 9, y, "open", (0, -1), tail=1)
    for dy in range(2, 15, 2):  # spiky fur on both sides
        _put(px, 8 - (dy // 2) % 2, y + dy, PAL["O"])
        _put(px, 22 + (dy // 2) % 2, y + dy, PAL["O"])
    if k < 1:
        _put(px, 4, 6, (255, 220, 0))


# ---- tricks: on demand from the web UI
FISH = [".##..#", "######", ".##..#"]  # 6x3, facing left


def _fish(px, x, y, flip=False):
    for r, row in enumerate(FISH):
        for c, ch in enumerate(row[::-1] if flip else row):
            if ch == "#":
                _put(px, x + c, y + r, (90, 170, 255) if c not in (0, 5) else (40, 110, 220))
    _put(px, x + (4 if flip else 1), y, (255, 255, 255))  # eye


def _sparkles(px, u, cx, cy):
    for k in range(4):
        a = u * 3 + k * math.pi / 2
        _put(px, round(cx + 9 * math.cos(a)), round(cy + 6 * math.sin(a)), (255, 230, 120))


def _act_flip(img, u, r):  # crouch, backflip in four 90-degree steps, land, sparkle
    if u < 0.4 or u > 1.4:
        draw_cat(img, 9, 17 if u < 0.4 else 16, "smug" if u > 1.6 else "open", (0, -1 if u < 0.4 else 0), tail=int(u * 4))
        if u > 1.4:
            _sparkles(img.load(), u, 15, 22)
        return
    p = (u - 0.4) / 1.0
    sprite = render.blank()
    draw_cat(sprite, 9, 16, "closed", tail=1)
    sprite = sprite.crop((8, 16, 25, 32)).rotate(-90 * int(p * 4), resample=Image.NEAREST)
    y = round(16 - 14 * math.sin(math.pi * p))
    img.paste(sprite, (8, y), sprite.convert("L").point(lambda v: 255 if v else 0))


def _act_feed(img, u, r):  # a fish treat drops into the bowl, nom nom, happy
    px = img.load()
    for x in range(22, 31):  # bowl
        _put(px, x, 31, (200, 60, 60))
    for x in range(21, 32):
        _put(px, x, 30, (230, 80, 80))
    if u < 1.0:  # falling
        _fish(px, 23, round(u * 27))
    elif u < 2.6:  # eaten in bites
        bite = int((u - 1.0) / 0.4)
        for k in range(max(0, 6 - bite * 2)):
            for dy in range(3):
                if FISH[dy][k] == "#":
                    _put(px, 23 + k, 27 + dy, (90, 170, 255))
        if int(u * 4) % 2:
            render.draw_text(img, 2, 3, "NOM", (255, 200, 120), font="small")
    else:
        _sprite(px, 22, 5, HEART, (250, 90, 130))
    near = 1.0 <= u < 2.6
    draw_cat(img, 11 if near else 7, 16, "closed" if 2.6 <= u else "open", (1, 0), tail=int(u * 4),
             paw="right" if near and int(u * 3) % 2 else None)


def _act_fish(img, u, r):  # waits by the pond, swipes a jumping fish out, shows it off
    px = img.load()
    for x in range(17, 32):
        for y in range(27, 32):
            _put(px, x, y, (20, 70, 150) if (x + y + int(u * 4)) % 5 else (60, 130, 220))
    if u < 2.0:  # swimming
        _fish(px, 18 + round((math.sin(u * 2) + 1) * 4), 28, flip=math.cos(u * 2) > 0)
        look = (1, 0)
    elif u < 2.6:  # jumps
        p = (u - 2.0) / 0.6
        _fish(px, 24 - round(p * 8), round(28 - math.sin(math.pi * p) * 14), flip=False)
        look = (1, -1)
    else:  # caught: hangs from the paw
        _fish(px, 1, 26)
        look = (0, 0)
    proud = u > 3.0
    y = round(16 - abs(math.sin((u - 3) * 6)) * 3) if proud and u < 4.2 else 16
    draw_cat(img, 4, y, "smug" if proud else "open", look, tail=int(u * 5),
             paw="right" if 2.3 < u < 2.7 else "left" if u >= 2.6 else None)
    if proud:
        _sparkles(px, u, 10, 22)


def _act_pet(img, u, r):  # purrs: eyes shut, tiny vibration, hearts
    px = img.load()
    for k in range(2):
        p = (u * 0.6 + k / 2) % 1
        _sprite(px, (3, 24)[k], 12 - round(p * 12), HEART, tuple(int(v * (1 - p * 0.6)) for v in (250, 90, 130)))
    if int(u * 2) % 2:
        render.draw_text(img, 9, 2, "PURR", (230, 170, 120), font="small")
    draw_cat(img, 9 + int(u * 8) % 2, 16, "closed", tail=int(u * 3))


TRICKS = {"flip": (_act_flip, 2.6), "feed": (_act_feed, 4), "fish": (_act_fish, 5), "pet": (_act_pet, 4)}
TRICK_LABELS = {"flip": "Do a flip", "feed": "Feed a treat", "fish": "Catch a fish", "pet": "Pet", "laser": "Laser pointer",
                "yarn": "Throw yarn", "knock": "Mug on a shelf…", "zoomies": "Zoomies", "peek": "Hide & seek"}

MOODS = {"startle": _act_startle, "ask": _act_ask, "greet": _act_greet, "work": _act_work, "dance": _act_dance, "sleep": None}
AWAY_SECS = 300  # no keyboard/mouse this long = you're away; cat naps

ACTS = {"idle": (_act_idle, 6), "laser": (_act_laser, 7), "yarn": (_act_yarn, 5), "knock": (_act_knock, 7),
        "sleep": (_act_sleep, 8), "peek": (_act_peek, 6), "zoomies": (_act_zoomies, 4)}


def schedule(start: float, seed: int):
    """Endless act sequence from a seed: idle between acts, never the same act twice in a row."""
    r = random.Random(seed)
    t, last = start, None
    while True:
        for name in ("idle", r.choice([a for a in ACTS if a not in ("idle", last)])):
            yield name, t, r.random()
            t += ACTS[name][1]
            last = name


class Cat:
    def __init__(self, start: float = 0.0, seed: int = 7):
        self._acts = schedule(start, seed)
        self.act, self.t0, self.seed = next(self._acts)
        self._next = next(self._acts)
        self.mood, self.mood_t0, self.away, self.greet_until = None, 0.0, False, 0.0
        self.trick: tuple[str, float] | None = None  # (name, start)

    def do(self, name: str, t: float) -> float:
        """Run a trick (or any mischief act) now. Returns its duration."""
        fn_dur = TRICKS.get(name) or ACTS.get(name)
        if not fn_dur:
            raise ValueError(f"unknown trick {name}")
        self.trick = (name, int(t * FPS) / FPS)
        return fn_dur[1]

    def busy(self, t: float) -> bool:
        return bool(self.trick) and t < self.trick[1] + (TRICKS.get(self.trick[0]) or ACTS[self.trick[0]])[1]

    def _mood(self, t: float, ctx: dict | None) -> str | None:
        """ctx: idle (secs since keyboard/mouse), claude (session states), music (bool), hour."""
        if not ctx:
            return None
        idle, claude = ctx["idle"], ctx["claude"]
        if ctx.get("clap"):
            return "startle"
        if "input" in claude:
            return "ask"
        night = ctx["hour"] >= 23 or ctx["hour"] < 6
        if idle > AWAY_SECS or (night and idle > 60):
            self.away = True
            return "sleep"
        if self.away:  # just came back
            self.away, self.greet_until = False, t + 4
        if t < self.greet_until:
            return "greet"
        if "working" in claude and t % 30 < 20:  # mostly helps, sometimes gets distracted
            return "work"
        if ctx["music"] and t % 40 < 14:  # dances in bursts so it doesn't get old
            return "dance"
        return None

    def frame(self, t: float, ctx: dict | None = None) -> Image.Image:
        t = int(t * FPS) / FPS  # quantize: at most FPS distinct frames per second
        while t >= self._next[1]:
            self.act, self.t0, self.seed = self._next
            self._next = next(self._acts)
        img = render.blank()
        if self.busy(t):  # asked for: beats every mood
            fn, _ = TRICKS.get(self.trick[0]) or ACTS[self.trick[0]]
            fn(img, t - self.trick[1], random.Random(1))
            return img
        mood = self._mood(t, ctx)
        if mood != self.mood:
            self.mood, self.mood_t0 = mood, t
        if mood:
            (MOODS[mood] or _act_sleep)(img, t - self.mood_t0, random.Random(0))
        else:
            fn, _ = ACTS[self.act]
            fn(img, max(0.0, t - self.t0), random.Random(self.seed))
        return img


if __name__ == "__main__":
    for name, (fn, dur) in ACTS.items():
        frames = set()
        for k in range(int(dur * FPS)):
            img = render.blank()
            fn(img, k / FPS, random.Random(1))
            frames.add(img.tobytes())
        assert len(frames) > 1 or name == "idle", name  # every act moves
    c = Cat(start=0, seed=3)
    seen = {c.act}
    for k in range(60 * FPS):
        a = c.frame(k / FPS)
        seen.add(c.act)
    assert len(seen) >= 4, seen  # a minute of cat covers several acts
    assert Cat(0, 3).frame(1.0).tobytes() == Cat(0, 3).frame(1.01).tobytes()  # quantized: no extra resends
    for name, fn in MOODS.items():
        if fn:
            assert len({(lambda im: (fn(im, k / FPS, random.Random(0)), im.tobytes())[1])(render.blank())
                        for k in range(16)}) > 1, name
    m = Cat(0, 3)
    ctx = {"idle": 0, "claude": [], "music": False, "hour": 14}
    for name, (fn, dur) in TRICKS.items():
        frames = set()
        for k in range(int(dur * FPS)):
            img = render.blank()
            fn(img, k / FPS, random.Random(1))
            frames.add(img.tobytes())
        assert len(frames) > 5, name
    c = Cat(0, 3)
    assert c.do("flip", 10.0) == 2.6 and c.busy(11) and not c.busy(12.7)
    asleep = c.frame(11, {"idle": 999, "claude": [], "music": False, "hour": 3})
    assert c.mood is None or c.mood != "sleep" or asleep  # trick wins over the nap
    try:
        c.do("explode", 0)
        raise AssertionError
    except ValueError:
        pass
    assert m._mood(0.5, {**ctx, "clap": True, "claude": ["input"]}) == "startle"
    assert m._mood(1, {**ctx, "claude": ["input", "working"]}) == "ask"
    assert m._mood(2, {**ctx, "idle": 400}) == "sleep"
    assert m._mood(3, ctx) == "greet" and m._mood(8, ctx) is None  # greets for 4s after you return
    assert m._mood(61, {**ctx, "claude": ["working"]}) == "work"
    assert m._mood(81, {**ctx, "music": True}) == "dance"
    assert m._mood(70, {**ctx, "hour": 23, "idle": 90}) == "sleep"
    print("ok", sorted(seen))
