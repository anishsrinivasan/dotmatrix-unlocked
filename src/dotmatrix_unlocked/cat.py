"""A mischievous pixel cat that lives on the panel and picks a random bit of mischief every few seconds.
frame(t) is a pure function of time within the current act, so the same t gives the same frame (no resends).
To add an act: write _act_<name>(img, u, r) (u = seconds into the act, r = per-act Random) and list it in ACTS.
It also has needs (full, energy, fun, love) that drift over real time; when one runs low it asks for it, and
you look after it by feeding, playing and petting (stroke it in the web UI)."""
import array
import math
import random
import re
import threading

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


def draw_cat(img, x, y, eyes="open", look=(0, 0), tail=0, paw=None, mouth=0):
    """eyes: open | closed | smug. look: (-1..1, -1..0). paw: None | 'left' | 'right' (raised).
    mouth: 0 closed, 1 ajar, 2 wide open (talking)."""
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
    if mouth:  # under the nose; wide open shows a tongue
        for mx, my in ([(6, 8)] if mouth == 1 else [(5, 8), (6, 8), (7, 8), (5, 9), (7, 9)]):
            _put(px, x + mx, y + my, PAL["K"])
        _put(px, x + 6, y + 9, PAL["P"] if mouth == 2 else PAL["K"])
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


def _bubble(img, text, colour=(255, 255, 255)):
    """Speech bubble in the top-right corner, pointing down-left at the cat."""
    px, w = img.load(), render.text_width(text) + 4
    x0 = 31 - w
    for x in range(x0, 32):
        for y in range(1, 9):
            if not ((x in (x0, 31)) and y in (1, 8)):
                _put(px, x, y, (235, 235, 240))
    _put(px, x0 + 2, 9, (235, 235, 240)); _put(px, x0 + 1, 10, (235, 235, 240))
    render.draw_text(img, x0 + 2, 3, text, colour, font="small")


def _act_chin(img, u, r):  # chin scratch: head tilted up, slow blink, louder purr
    px = img.load()
    for k in range(3):
        p = (u * 0.8 + k / 3) % 1
        _sprite(px, (1, 13, 26)[k], 13 - round(p * 13), HEART, tuple(int(v * (1 - p * 0.6)) for v in (255, 110, 170)))
    draw_cat(img, 9 + int(u * 10) % 2, 15, "smug" if int(u * 1.5) % 3 else "closed", (0, -1), tail=int(u * 4))


def _act_rub(img, u, r):  # trusts you: belly rub allowed, wiggles happily
    px = img.load()
    _sparkles(px, u, 15, 22)
    draw_cat(img, 9 + round(math.sin(u * 9)), 16, "closed", tail=int(u * 6), paw=("left", "right")[int(u * 3) % 2])
    if int(u * 2) % 2:
        render.draw_text(img, 9, 2, "PRRR", (255, 150, 200), font="small")


def _act_trap(img, u, r):  # the belly is a trap: grabs your hand with both paws, bunny-kicks, lets go smug
    if u < 1.6:
        render.draw_text(img, 25, 2, "!", (255, 220, 0))
        draw_cat(img, 9, 17, "open", (0, 1), tail=1, paw=("left", "right")[int(u * 8) % 2])
        if int(u * 4) % 2:
            render.draw_text(img, 1, 3, "CHOMP", (255, 120, 90), font="small")
    else:
        draw_cat(img, 9, 16, "smug", (1, 0), tail=int(u * 2))


def _act_swat(img, u, r):  # petted too much: ears back, hiss, swats
    draw_cat(img, 8 + int(u * 7) % 3, 16, "smug", (0, 0), tail=int(u * 10), paw="right" if int(u * 5) % 2 else None)
    _bubble(img, "HSS", (220, 40, 40) if int(u * 4) % 2 else (255, 120, 60))


def _act_refuse(img, u, r):  # already full: sniffs the treat and turns away
    _bubble(img, "FULL")
    draw_cat(img, 7 - min(3, int(u * 3)), 16, _blink(u * 3) if u < 1 else "smug", (-1, 0), tail=int(u * 4))


# ---- Talking Tom: the browser hears you, the cat says it back (squeaky) through your speakers
def _act_listen(img, u, r):  # ears up, leaning in, sound waves coming in from the side
    px = img.load()
    for k in range(3):
        p = (u * 1.2 + k / 3) % 1
        x = 2 + round(p * 5)
        for dy in range(-k - 1, k + 2):
            _put(px, x - abs(dy) // 2, 18 + dy, tuple(int(v * (1 - p * 0.7)) for v in (120, 200, 255)))
    draw_cat(img, 11, 16, "open", (-1, 0), tail=int(u * 2))
    _bubble(img, "?" if int(u * 2) % 2 else " ? ", (30, 110, 230))  # all ears


def _act_speak(img, u, env):  # mouth follows the loudness of the playback; env = levels 0..1 at TALK_HZ
    lvl = env[min(int(u * TALK_HZ), len(env) - 1)] if env else 0
    mouth = 2 if lvl > 0.55 else 1 if lvl > 0.15 else 0
    draw_cat(img, 9, 16 - (mouth == 2), "open" if lvl > 0.05 else _blink(u), (0, 0), tail=int(u * 6), mouth=mouth)
    for k in range(round(lvl * 3)):  # sound lines out of the mouth
        _put(img.load(), 22 + k * 2, 20 - k, (255, 230, 120))
        _put(img.load(), 22 + k * 2, 26 + k, (255, 230, 120))


TALK_HZ = 20  # loudness levels per second the browser sends with a reply
LISTEN_SECS = 10  # listening pose holds this long unless the reply (or silence) comes first


# ---- needs: what it asks for when one runs low
def _act_hungry(img, u, r):  # by the empty bowl, looks at it, looks at you
    px = img.load()
    for x in range(21, 32):
        _put(px, x, 30, (230, 80, 80))
    for x in range(22, 31):
        _put(px, x, 31, (200, 60, 60))
    ask = int(u / 2) % 2
    draw_cat(img, 6, 16, _blink(u), (1, 1) if not ask else (0, 0), tail=int(u * 2))
    if ask:
        _bubble(img, "FEED?", (230, 80, 80))


def _act_lonely(img, u, r):  # wants you: sits close, slow wave
    draw_cat(img, 9, 16, _blink(u), (0, 0), tail=int(u * 2), paw="left" if int(u * 1.5) % 2 else None)
    if int(u / 2) % 2:
        _bubble(img, "PET?", (250, 90, 130))


def _act_bored(img, u, r):  # nudges its yarn ball, sighs
    px = img.load()
    bx = 24 + round(math.sin(u * 1.5) * 2)
    for dx, dy in ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, -1), (1, 2)):
        _put(px, bx + dx, 28 + dy, (230, 70, 120) if (dx + dy) % 2 else (190, 40, 90))
    draw_cat(img, 6, 16, "smug", (1, 1), tail=int(u), paw="right" if int(u) % 3 == 0 else None)
    if int(u / 2) % 2:
        _bubble(img, "PLAY?", (120, 200, 255))


TRICKS = {"flip": (_act_flip, 2.6), "feed": (_act_feed, 4), "fish": (_act_fish, 5), "pet": (_act_pet, 4),
          "chin": (_act_chin, 3), "rub": (_act_rub, 3), "trap": (_act_trap, 2.6), "swat": (_act_swat, 2.5),
          "refuse": (_act_refuse, 2.5), "listen": (_act_listen, LISTEN_SECS), "speak": (_act_speak, 0)}
TRICK_LABELS = {"flip": "Do a flip", "feed": "Feed a treat", "fish": "Catch a fish", "pet": "Pet", "laser": "Laser pointer",
                "yarn": "Throw yarn", "knock": "Mug on a shelf…", "zoomies": "Zoomies", "peek": "Hide & seek"}

MOODS = {"startle": _act_startle, "ask": _act_ask, "greet": _act_greet, "work": _act_work, "dance": _act_dance, "sleep": None,
         "tired": None, "hungry": _act_hungry, "lonely": _act_lonely, "bored": _act_bored}
NEEDS = ("full", "energy", "fun", "love")
DECAY = {"full": -6, "energy": -5, "fun": -10, "love": -5}  # points per hour awake (0..100)
NAP_ENERGY = 30  # per hour while asleep
LOW, NAP_AT, WAKE_AT = 30, 15, 70
PLAY = {"fun": 12, "energy": -5}
PERSONA = ("You are Pixel, a small, playful, slightly sassy cat who lives on an LED panel on your human's desk. Talk like a "
           "cat would if it could talk: one or two short sentences, under 25 words, no emojis, nothing in asterisks. If what "
           "they say calls for it, end with one action in brackets: [flip], [fish], [laser], [yarn], [zoomies], [peek], "
           "[knock], or [feed] (only when they give you food).")
DOABLE = ("flip", "feed", "fish", "laser", "yarn", "zoomies", "peek", "knock")  # what it may choose to do after talking
SPOKEN = 14  # characters a second the browser speaks them, for the mouth
VOICE = ("You are the voice of a cartoon cat. Say the user's message out loud exactly as written, word for word, in a "
         "high, bright, playful cat voice, a little purr in it. Don't answer it or add anything, except an optional "
         "short meow at the start.")
VOICE_RATE = 1.2  # the voice is played a little fast and high, Talking Tom style, and still easy to follow


def levels(pcm: bytes, rate: float = VOICE_RATE) -> list[float]:
    """Loudness (0..1) of 24 kHz 16-bit mono speech per 1/TALK_HZ s, played at rate x speed: drives the mouth."""
    a, step = array.array("h", pcm[:len(pcm) // 2 * 2]), int(24000 * rate / TALK_HZ)
    env = [math.sqrt(sum(v * v for v in a[i:i + step]) / step) for i in range(0, len(a), step)]
    peak = max(env, default=0) or 1
    return [round(v / peak, 2) for v in env]
EFFECTS = {"feed": {"full": 35}, "fish": {"fun": 15, "full": 10, "energy": -5}, "pet": {"love": 6}, "chin": {"love": 8},
           "rub": {"love": 10}, "speak": {"love": 3, "fun": 2}, "trap": {"love": 1, "fun": 5}, "swat": {"love": -4},
           **{k: PLAY for k in ("flip", "laser", "yarn", "zoomies", "knock", "peek")}}
OVERPET = 14  # strokes within 20 s before it has had enough
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
        self.trick: tuple[str, float, float] | None = None  # (name, start, end)
        self.needs, self.needs_at = {k: 70.0 for k in NEEDS}, start
        self.napping, self.strokes, self.grumpy_until, self.env, self.chat = False, [], 0.0, [], []
        self._lock = threading.RLock()  # the display, the web UI and the needs clock all touch it

    def state(self) -> dict:
        return {"needs": {k: round(v, 1) for k, v in self.needs.items()}, "at": self.needs_at, "napping": self.napping}

    def load(self, d: dict) -> None:
        self.needs.update({k: max(0.0, min(100.0, float(v))) for k, v in d.get("needs", {}).items() if k in NEEDS})
        self.needs_at, self.napping = float(d.get("at", self.needs_at)), bool(d.get("napping"))

    def _apply(self, delta: dict) -> None:
        for k, v in delta.items():
            self.needs[k] = max(0.0, min(100.0, self.needs[k] + v))

    def tick(self, t: float, asleep: bool) -> None:
        """Needs drift with real time, also while the app was closed (up to two days)."""
        with self._lock:
            self._tick(t, asleep)

    def _tick(self, t: float, asleep: bool) -> None:
        h = max(0.0, min(t - self.needs_at, 48 * 3600)) / 3600
        self.needs_at = max(t, self.needs_at)
        self._apply({k: v * h for k, v in DECAY.items() if not (asleep and k == "energy")})
        if asleep:
            self._apply({"energy": NAP_ENERGY * h})
        if self.needs["energy"] < NAP_AT:
            self.napping = True
        elif self.needs["energy"] >= WAKE_AT:
            self.napping = False

    def _start(self, name: str, t: float, extend: bool = False) -> float:
        dur = (TRICKS.get(name) or ACTS[name])[1]
        if extend and self.trick and self.trick[0] == name and t < self.trick[2]:
            self.trick = (name, self.trick[1], t + dur)  # keep the animation going, don't restart it
        else:
            self.trick = (name, int(t * FPS) / FPS, t + dur)
        return dur

    def do(self, name: str, t: float) -> float:
        """Run a trick (or any mischief act) now and look after its needs. Returns its duration."""
        if name not in TRICKS and name not in ACTS:
            raise ValueError(f"unknown trick {name}")
        if name == "feed" and self.needs["full"] > 90:
            name = "refuse"
        self._apply(EFFECTS.get(name, {}))
        self.napping = False  # anything you do wakes it up
        return self._start(name, t)

    def pet(self, zone: str, t: float) -> tuple[str, float]:
        """One stroke. zone: head | chin | belly. Returns (reaction, seconds it shows)."""
        if zone not in ("head", "chin", "belly"):
            raise ValueError("pet: head, chin or belly")
        if t < self.grumpy_until:
            return "grumpy", 0.0
        self.strokes = [s for s in self.strokes if t - s < 20] + [t]
        if len(self.strokes) > OVERPET:
            self.strokes, self.grumpy_until = [], t + 10
            self._apply(EFFECTS["swat"])
            return "swat", self._start("swat", t)
        name = {"head": "pet", "chin": "chin"}.get(zone) or ("rub" if self.needs["love"] >= 80 else "trap")
        if not (self.trick and self.trick[0] == name and t < self.trick[2]):  # love counts per petting, not per pixel
            self._apply(EFFECTS[name])
        self.napping = False
        return name, self._start(name, t, extend=True)

    def talk(self, mode: str, t: float, env: list | None = None) -> float:
        """mode: listen (you're talking) | speak (playing it back; env = loudness per 1/TALK_HZ s) | done."""
        if mode == "done":
            if self.trick and self.trick[0] in ("listen", "speak"):
                self.trick = None
            return 0.0
        if mode == "listen":
            self.napping = False
            return self._start("listen", t, extend=True)
        if mode != "speak" or not isinstance(env, list) or not 0 < len(env) <= 30 * TALK_HZ:
            raise ValueError("talk: listen | speak with env (up to 30 s of levels) | done")
        self.env = [max(0.0, min(1.0, float(v))) for v in env]
        self._apply(EFFECTS["speak"])
        self.trick = ("speak", t, t + len(env) / TALK_HZ + 0.3)
        return len(env) / TALK_HZ + 0.3

    def prompt(self, said: str) -> list[dict]:
        """Chat messages for a small LLM: who it is, how it feels now, the last few exchanges, then what you said."""
        feel = {"hungry": "You're hungry.", "lonely": "You want attention.", "bored": "You're bored.",
                "tired": "You're sleepy."}.get(self.wants(), "You're content.")
        return [{"role": "system", "content": f"{PERSONA} {feel}"}, *self.chat, {"role": "user", "content": said[:300]}]

    @staticmethod
    def reply(reply: str) -> tuple[str, str | None]:
        """The model's reply -> (the words to speak, a trick it chose to do after them)."""
        trick = next((w for w in re.findall(r"\[(\w+)\]", reply.lower()) if w in DOABLE), None)
        return " ".join(re.sub(r"\[[^\]]*\]|\*[^*]*\*|[^\w\s.,!?'-]", " ", reply).split())[:240] or "Meow.", trick

    def answer(self, said: str, reply: str, t: float, pcm: bytes = b"") -> tuple[str, str | None, float]:
        """Say the model's reply, the mouth following the voice (pcm) or, for the browser's voice, the vowels.
        Returns (the words to speak, a trick it chose to do after, seconds of talking)."""
        words, trick = self.reply(reply)
        self.chat = (self.chat + [{"role": "user", "content": said[:300]}, {"role": "assistant", "content": reply[:300]}])[-6:]
        level = [0.9 if c in "aeiouy" else 0.5 if c.isalpha() else 0.05 for c in words.lower()]
        env = levels(pcm) if pcm else [level[int(i * SPOKEN / TALK_HZ)] for i in range(int(len(level) * TALK_HZ / SPOKEN))]
        env = env or [0.5]
        return words, trick, self.talk("speak", t, env[:30 * TALK_HZ])

    def wants(self) -> str | None:
        """The need it would ask you for right now, lowest first."""
        if self.napping:
            return "tired"
        k = min(("full", "love", "fun"), key=self.needs.get)
        return {"full": "hungry", "love": "lonely", "fun": "bored"}[k] if self.needs[k] < LOW else None

    def busy(self, t: float) -> bool:
        return bool(self.trick) and t < self.trick[2]

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
        want = self.wants()
        if want == "tired":
            return want
        if "working" in claude and t % 30 < 20:  # mostly helps, sometimes gets distracted
            return "work"
        if ctx["music"] and t % 40 < 14:  # dances in bursts so it doesn't get old
            return "dance"
        if want and t % 40 < 16:  # asks in bursts, mischief in between
            return want
        return None

    def frame(self, t: float, ctx: dict | None = None) -> Image.Image:
        with self._lock:
            return self._frame(int(t * FPS) / FPS, ctx)  # quantize: at most FPS distinct frames per second

    def _frame(self, t: float, ctx: dict | None) -> Image.Image:
        if ctx is not None:
            self.tick(t, self.mood in ("sleep", "tired"))
        while t >= self._next[1]:
            self.act, self.t0, self.seed = self._next
            self._next = next(self._acts)
        img = render.blank()
        if self.busy(t):  # asked for: beats every mood
            fn, _ = TRICKS.get(self.trick[0]) or ACTS[self.trick[0]]
            fn(img, t - self.trick[1], self.env if fn is _act_speak else random.Random(1))
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
        if name == "speak":
            continue  # driven by the browser's levels; checked below
        frames = set()
        for k in range(int(dur * FPS)):
            img = render.blank()
            fn(img, k / FPS, random.Random(1))
            frames.add(img.tobytes())
        assert len(frames) > 5, name
    c = Cat(0, 3)
    # talking with an LLM: picks a trick from its reply, speaks only the words, remembers the last few exchanges
    w, trick, secs = c.answer("want fish?", "*purrs* Ooh, fish! Gimme gimme. [fish] 🐟", 1.0)
    assert (w, trick) == ("Ooh, fish! Gimme gimme.", "fish") and 1 < secs < 3 and c.trick[0] == "speak"
    assert c.answer("x", "[delete] Meow", 2)[1] is None and c.answer("x", "[]", 2)[0] == "Meow."
    tone = array.array("h", [int(8000 * math.sin(k / 5)) if k < 24000 else 0 for k in range(48000)]).tobytes()
    env = levels(tone)  # one loud second, one silent, played 1.2x fast
    assert len(env) == 34 and env[0] == 1.0 and env[-1] == 0.0
    assert abs(c.answer("hi", "Meow there.", 3, tone)[2] - (34 / TALK_HZ + 0.3)) < 0.01
    msgs = c.prompt("hi")
    assert msgs[0]["role"] == "system" and msgs[-1] == {"role": "user", "content": "hi"} and len(msgs) == 8
    assert c.do("flip", 10.0) == 2.6 and c.busy(11) and not c.busy(12.7)
    # needs drift, and it asks for the lowest one
    n = Cat(0, 3)
    n.tick(3600 * 6, asleep=False)  # six hours alone: fun 70-60 -> 10, full 34, love 40
    assert n.needs["fun"] == 10 and n.wants() == "bored"
    assert n._mood(3600 * 6 + 1, ctx) == "bored" and n._mood(3600 * 6 + 30, ctx) is None  # asks in bursts
    n.do("yarn", 0) and n.do("laser", 0) and n.do("fish", 0)
    assert n.needs["fun"] > LOW and n.wants() is None
    n.needs["full"] = 20
    assert n.wants() == "hungry"
    assert n.do("feed", 0) == 4 and n.needs["full"] == 55 and n.wants() is None
    n.needs["full"] = 95
    n.do("feed", 0)
    assert n.trick[0] == "refuse" and n.needs["full"] == 95  # won't overeat
    n.needs["energy"] = 10
    n.tick(n.needs_at, False)
    assert n.wants() == "tired" and n._mood(1, ctx) == "tired"  # naps even while you're here
    n.tick(n.needs_at + 3600 * 2, asleep=True)
    assert not n.napping and n.wants() != "tired"  # ...and wakes up rested
    late = Cat(0, 3)
    late.tick(10 ** 9, False)
    assert all(v >= 0 for v in late.needs.values())  # clamped, and offline time capped
    # petting: zones, keeps one animation going while you stroke, belly is a trap until it trusts you
    p = Cat(0, 3)
    love = p.needs["love"]
    assert p.pet("head", 1.0)[0] == "pet" and p.pet("head", 1.5)[0] == "pet" and p.trick[1] == 1.0
    assert p.needs["love"] == love + 6 and p.busy(5.4)  # one petting, extended
    assert p.pet("chin", 6.0)[0] == "chin"
    p.needs["love"] = 50
    assert p.pet("belly", 10.0)[0] == "trap"
    p.needs["love"] = 90
    assert p.pet("belly", 14.0)[0] == "rub"
    for k in range(OVERPET):
        p.pet("head", 15 + k * 0.5)
    assert p.trick[0] == "swat" and p.pet("head", 23)[0] == "grumpy" and p.pet("head", 30)[0] == "pet"
    # talking: listen pose holds while you speak, the mouth follows the reply's loudness, then back to normal
    tk = Cat(0, 3)
    assert tk.talk("listen", 1.0) == LISTEN_SECS and tk.busy(5) and tk.trick[0] == "listen"
    env = [0.0, 0.3, 1.0, 1.0, 0.3, 0.0] * 4
    assert abs(tk.talk("speak", 6.0, env) - (len(env) / TALK_HZ + 0.3)) < 1e-9 and tk.trick[0] == "speak"
    mouths = {tk.frame(6.0 + k / 8).crop((14, 24, 18, 26)).tobytes() for k in range(8)}
    assert len(mouths) >= 2  # opens and closes
    assert not tk.busy(6.0 + len(env) / TALK_HZ + 0.5)
    tk.talk("listen", 20.0); tk.talk("done", 21.0)
    assert not tk.busy(21.5)
    for bad in (("speak", None), ("speak", [0.1] * 10 ** 4), ("shout", [1.0])):
        try:
            tk.talk(bad[0], 0, bad[1])
            raise AssertionError(bad)
        except ValueError:
            pass
    q = Cat(0, 3)
    q.load({"needs": {"full": 5, "bogus": 1}, "at": 123.0})
    assert q.needs["full"] == 5 and q.needs_at == 123.0 and "bogus" not in q.state()["needs"]
    for name in ("hungry", "lonely", "bored"):
        assert len({(lambda im: (MOODS[name](im, k / 2, random.Random(0)), im.tobytes())[1])(render.blank())
                    for k in range(10)}) > 1, name
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
