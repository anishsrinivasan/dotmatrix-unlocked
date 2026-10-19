"""Owns the BLE link; serves the web UI and a small JSON API on 127.0.0.1."""
import asyncio
import base64
import io
import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request
import zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from . import __version__
from . import cat
from . import device
from . import mic
from . import game
from . import lyrics
from . import markets
from . import render
from . import skins
from . import system
from . import video
PORT = int(os.environ.get("DOTMATRIX_PORT", "7766"))
HOME = system.config_dir()
CONFIG_FILE, GIF_DIR, CAT_FILE = HOME / "config.json", HOME / "gifs", HOME / "cat.json"
UI_FILE = Path(__file__).with_name("ui.html")

WEATHER_EVERY, WEATHER_STALE = 15 * 60, 60 * 60
MUSIC_POLL = 3
MARKETS_EVERY = 5 * 60  # snapdata is daily, Yahoo quotes move; only fetched while the skin is in use
MIN_SEND_GAP = 1.0      # rate limit between frames
HEARTBEAT = 30          # ping when nothing else was sent
MAX_MISSES = 3          # consecutive unacked writes -> reconnect
HARD_DEADLINE = 5 * 60  # no ack at all this long -> exit, the service manager restarts us
SESSION_TTL = 3 * 3600  # ponytail: crashed sessions never send SessionEnd; dropped after 3h silent
MAX_BODY = 12_000_000
TIMER_RING = 15  # seconds TIME UP flashes before the display goes back
GIF_NAME = re.compile(r"^[a-z0-9_-]{1,40}\.gif$")

SKINS = ("dashboard", "album", "vinyl", "gif", "visualizer", "games", "video", "cat", "markets", "karaoke")
DEFAULTS = {**render.DEFAULT_CFG, "skin": "dashboard", "brightness": 80, "gamma": 2.2, "interrupt_on_input": True,
            "city": "", "lat": None, "lon": None, "gif": None, "giphy_key": "",
            "saved_skins": {}, "game": "snake", "vis_style": "bars",
            "markets": ["GOLD", "SILVER", "USDINR", "AAPL", "NVDA"], "markets_vs": "prev", "markets_show": "both", "lyrics_offset": 0.0}

# Hook event -> session state. https://code.claude.com/docs/en/hooks
INPUT_NOTIFICATIONS = {"permission_prompt", "elicitation_dialog", "elicitation_url_dialog", "agent_needs_input"}
ASK_TOOLS = {"AskUserQuestion", "ExitPlanMode"}
EVENT_STATE = {"SessionStart": "waiting", "UserPromptSubmit": "working", "PostToolUse": "working",
               "PermissionRequest": "input", "Stop": "waiting", "StopFailure": "waiting"}

log = logging.getLogger("daemon")


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        saved = json.loads(CONFIG_FILE.read_text())
        cfg.update({k: v for k, v in saved.items() if k in DEFAULTS})
        if "layout" not in saved:  # pre-layout config: carry over row toggles and clock color
            show = saved.get("show", {})
            for m in cfg["layout"]:
                m["on"] = show.get(m["id"], True)
                if m["id"] == "clock" and "clock_color" in saved:
                    m["color"] = saved["clock_color"]
    except FileNotFoundError:
        pass
    return cfg


def _layout(v) -> list:
    """Ordered module stack: known ids, at most 12, at most one space-filling module."""
    if not isinstance(v, list) or len(v) > 12 or not all(isinstance(m, dict) and m.get("id") in render.MODULES for m in v):
        raise ValueError("layout: up to 12 known modules")
    if sum(render.MODULES[m["id"]]["height"] is None for m in v) > 1:
        raise ValueError("only one Now playing module")
    out = []
    for m in v:
        if m.get("font", "regular") not in render.FONTS:
            raise ValueError(f"unknown font {m.get('font')}")
        out.append({"id": m["id"], "on": bool(m.get("on", True)), "font": m.get("font", "regular"),
                    "color": list(_rgb(m.get("color", [255, 255, 255])))})
    return out


def geocode(city: str) -> dict:
    q = urllib.parse.urlencode({"name": city, "count": 1})
    res = json.loads(urllib.request.urlopen(f"https://geocoding-api.open-meteo.com/v1/search?{q}", timeout=10).read())
    if not res.get("results"):
        raise ValueError(f"city not found: {city}")
    r = res["results"][0]
    return {"city": r["name"], "lat": r["latitude"], "lon": r["longitude"]}


_air_cities: list | None = None


def air_pm25(lat: float, lon: float) -> float | None:
    """PM2.5 (µg/m³) averaged over the CPCB stations of the nearest Indian city within ~50 km; None elsewhere.
    snapdata.dev, free, no key, refreshed every 3 hours."""
    global _air_cities
    base = "https://snapdata.dev/api/v1/aqi/in/"
    if _air_cities is None:
        _air_cities = [c for c in markets._get(base + "index.json")["cities"] if c.get("latitude") is not None]
    dist = lambda c: (c["latitude"] - lat) ** 2 + (c["longitude"] - lon) ** 2
    near = min(_air_cities, key=dist, default=None)
    if not near or dist(near) > 0.25:  # ponytail: degrees², ~50 km; fine for picking a city
        return None
    vals = [r["avg"] for r in markets._get(base + f"city/{near['slug']}.json")["records"]
            if r["pollutant"] == "PM2.5" and r["avg"] is not None]
    return sum(vals) / len(vals) if vals else None


def validated(cfg: dict, patch: dict) -> dict:
    """Merge a UI patch into a copy of cfg. Raises ValueError on bad input."""
    new = json.loads(json.dumps(cfg))
    for k, v in patch.items():
        if k == "skin":
            if v not in SKINS:
                raise ValueError(f"unknown skin {v}")
            new[k] = v
        elif k == "brightness":
            new[k] = max(5, min(100, int(v)))
        elif k == "gamma":
            new[k] = max(1.0, min(3.5, float(v)))
        elif k == "anim_fps":
            new[k] = max(0.2, min(2.0, float(v)))
        elif k == "lyrics_offset":  # seconds; + shows lines earlier (Bluetooth lag, players that report late)
            new[k] = max(-3.0, min(3.0, round(float(v), 1)))
        elif k == "page_secs":
            new[k] = max(1.0, min(30.0, float(v)))
        elif k == "vis_style":
            if v not in skins.Visualizer.STYLES:
                raise ValueError(f"unknown visualizer style {v}")
            new[k] = v
        elif k == "game":
            if v not in game.GAMES:
                raise ValueError(f"unknown game {v}")
            new[k] = v
        elif k == "layout":
            new[k] = _layout(v)
        elif k == "markets":
            new[k] = markets.valid(v)
        elif k == "markets_vs":
            new[k] = markets.valid_vs(v)
        elif k == "markets_show":
            if v not in markets.SHOWS:
                raise ValueError(f"markets: show one of {markets.SHOWS}")
            new[k] = v
        elif k == "saved_skins":
            if not isinstance(v, dict) or len(v) > 30:
                raise ValueError("saved_skins: up to 30 named layouts")
            new[k] = {str(n).strip()[:24]: _layout(l) for n, l in v.items() if str(n).strip()}
        elif k in ("clock_24h", "interrupt_on_input"):
            new[k] = bool(v)
        elif k == "city":
            if str(v).strip() and str(v).strip() != cfg["city"]:
                new.update(geocode(str(v).strip()[:80]))
        elif k == "giphy_key":
            new[k] = re.sub(r"[^A-Za-z0-9]", "", str(v))[:64]
        elif k == "gif":
            if v is not None and not (GIF_NAME.match(v) and (GIF_DIR / v).exists()):
                raise ValueError("unknown gif")
            new[k] = v
        else:
            raise ValueError(f"unknown setting {k}")
    return new


def _rgb(c) -> tuple:
    if isinstance(c, str):
        c = [int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    r, g, b = c
    return tuple(max(0, min(255, int(v))) for v in (r, g, b))


class State:
    def __init__(self):
        self.cfg = load_config()
        device.set_gamma(self.cfg["gamma"])
        self.weather: dict | None = None
        self.weather_wake: asyncio.Event | None = None
        self.music: dict | None = None     # {title, artist, album, art: Image|None, key}
        self.last_art: Image.Image | None = None  # album skin keeps the last cover after music stops
        self.scenes: dict[str, dict] = {}  # id -> {priority, expires, img}
        self.sessions: dict[str, dict] = {}  # session_id -> {state, at, cwd}
        self.connected = False
        self.last_ack = time.monotonic()
        self.current = "dashboard"
        self.address: str | None = device.saved_address()
        self.game: game.Game | None = None
        self.video: video.Player | None = None
        self.video_error: str | None = None
        self.cat, self.cat_draft = cat.Cat(time.time(), seed=int(time.time())), cat.Cat(time.time(), seed=1)
        try:  # its needs survive restarts (and keep drifting while we're off)
            self.cat.load(json.loads(CAT_FILE.read_text()))
        except (OSError, ValueError):
            pass
        self.timer: dict | None = None
        self.cat_until = 0.0  # a requested trick shows the cat over other skins until then
        self.mic = mic.Mic()
        self.idle = 0.0  # seconds since last keyboard/mouse input on the Mac  # {end, total, label}: wall-clock end time
        self.vis = skins.Visualizer()
        self.vis_draft = skins.Visualizer(seed=1)  # web preview animates on its own instance
        self.preview: tuple[str, bytes] = ("image/png", b"")
        self.quotes: dict = {}  # (markets id, compare-with) -> (value, change %)
        self.markets_wanted = 0.0  # last time the markets skin was previewed
        self.markets_wake: asyncio.Event | None = None
        self.markets_draft: tuple[list[str], str] = ([], "prev")  # what the preview shows
        self.lyrics: tuple[str, list | None] = ("", None)  # (track key, synced lines; [] = none found)
        self.lyrics_wanted = 0.0  # last time the karaoke skin was previewed
        self._gifs: dict[str, tuple[str, bytes, bytes]] = {}  # key -> (key, preview gif, gamma-corrected gif)

    def want_markets(self, items: list[str], vs: str) -> None:
        self.markets_wanted, self.markets_draft = time.time(), (items, vs)
        if self.markets_wake:
            self.loop.call_soon_threadsafe(self.markets_wake.set)

    def cat_ctx(self, clap: bool = False) -> dict:
        states = [v["state"] for v in self.sessions.values()]
        return {"idle": self.idle, "claude": states, "music": bool(self.music), "hour": datetime.now().hour, "clap": clap}

    def event(self, ev: dict) -> None:
        sid, name = ev.get("session_id"), ev.get("hook_event_name")
        if not sid:
            return
        if name == "SessionEnd":
            self.sessions.pop(sid, None)
            return
        new = EVENT_STATE.get(name)
        if name == "PreToolUse":
            new = "input" if ev.get("tool_name") in ASK_TOOLS else "working"
        elif name == "Notification" and ev.get("notification_type") in INPUT_NOTIFICATIONS:
            new = "input"
        if new:
            self.sessions[sid] = {"state": new, "at": time.time(), "cwd": ev.get("cwd", "")}

    def _gif_for(self, key: str, build) -> tuple[str, bytes, bytes]:
        key = f"{key}|g{self.cfg['gamma']}"
        if key not in self._gifs:
            frames = build()  # [(img, delay)]
            imgs, delays = [f for f, _ in frames], [d for _, d in frames]
            if len(self._gifs) >= 6:  # small LRU-ish cache shared by the display and draft previews
                self._gifs.pop(next(iter(self._gifs)))
            self._gifs[key] = (key, skins.to_gif(imgs, delays), skins.fit([(device.corrected(f, photo=True), d) for f, d in frames]))
        return self._gifs[key]

    def output(self, cfg: dict | None = None) -> tuple[str, str, object]:
        """(name, 'frame', Image) or (name, 'gif', (key, preview_gif, device_gif)).
        cfg given = render a draft for the web preview: no scenes, no state pruning."""
        draft = cfg is not None
        now, dt, cfg = time.time(), datetime.now(), cfg or self.cfg
        if not draft:
            self.scenes = {k: v for k, v in self.scenes.items() if v["expires"] > now}
            self.sessions = {k: v for k, v in self.sessions.items() if now - v["at"] < SESSION_TTL}
        if self.scenes and not draft:
            sid, s = max(self.scenes.items(), key=lambda kv: kv[1]["priority"])
            return sid, "frame", s["img"]
        tm = self.timer if not draft else None
        if tm and now > tm["end"] + TIMER_RING:
            self.timer = tm = None
        if tm and now >= tm["end"]:  # ringing beats games and video
            return "timer", "frame", render.timer(0, tm["total"], tm["label"], now)
        if self.game and not draft:
            if self.game.tick():
                return type(self.game).__name__.lower(), "frame", self.game.frame()
            self.game = None  # idle: back to the skin
        if self.video and not draft:
            if f := self.video.frame():
                return "video", "frame", f
            if self.video.error:
                self.video_error, self.video = self.video.error, None
        states = [v["state"] for v in sorted(self.sessions.values(), key=lambda v: v["cwd"])]
        weather = self.weather if self.weather and now - self.weather["at"] < WEATHER_STALE else None
        music, skin = self.music, cfg["skin"]
        dash = ("dashboard", "frame", render.dashboard(dt, now, cfg, weather, states, music))
        if skin == "dashboard" or ("input" in states and cfg["interrupt_on_input"]):
            return dash
        if now < self.cat_until and not draft:
            return "cat", "frame", self.cat.frame(now)
        if tm:
            return "timer", "frame", render.timer(tm["end"] - now, tm["total"], tm["label"], now)
        if skin == "cat":
            return "cat", "frame", (self.cat_draft if draft else self.cat).frame(now, self.cat_ctx(self.mic.clapped()))
        if skin == "video":
            return "video", "frame", skins.video_idle()
        if skin == "games":
            return "games", "frame", game.attract(cfg["game"])
        if skin == "visualizer":
            return "visualizer", "frame", (self.vis_draft.frame(now, True, cfg["vis_style"]) if draft
                                            else self.vis.frame(now, bool(music), cfg["vis_style"], self.mic.bands if self.mic.live else None))
        if skin == "markets":
            quotes = {i: q for (i, vs), q in self.quotes.items() if vs == cfg["markets_vs"]}
            return "markets", "frame", markets.frame(cfg["markets"], quotes, now, cfg["page_secs"], cfg["markets_show"])
        if skin == "karaoke":
            if not music:
                return "karaoke", "frame", skins.nothing_playing()
            lines = self.lyrics[1] if self.lyrics[0] == music["key"] else None
            pos = music["pos"] + (now - music["at"]) + cfg["lyrics_offset"] if music.get("pos") is not None else None
            return "karaoke", "frame", lyrics.frame(lines, pos, music["title"])
        if skin == "album":
            art = (music and music["art"]) or self.last_art
            return "album", "frame", skins.album(art) if art else skins.nothing_playing()
        if skin == "vinyl":
            art = music["art"] if music else None
            return "vinyl", "gif", self._gif_for(f"vinyl|{music['key'] if music else 'idle'}",
                                                lambda: [(f, 120) for f in skins.vinyl_frames(art)])
        if skin == "gif" and cfg["gif"] and (GIF_DIR / cfg["gif"]).exists():
            return "gif", "gif", self._gif_for(f"gif|{cfg['gif']}",
                                               lambda: skins.normalize_gif((GIF_DIR / cfg["gif"]).read_bytes()))
        return dash


state = State()


def parse_scene(body: dict) -> tuple[str, dict]:
    """{id?, text|image(b64), color?, bg?, ttl?, priority?}"""
    sid = str(body.get("id", "scene"))[:64]
    ttl = max(1, min(float(body.get("ttl", 30)), 24 * 3600))
    if body.get("image"):
        img = skins.album(Image.open(io.BytesIO(base64.b64decode(body["image"]))))
    else:
        img = render.message(str(body.get("text", ""))[:200], _rgb(body.get("color", (255, 255, 255))),
                             _rgb(body.get("bg", (0, 0, 0))))
    return sid, {"priority": int(body.get("priority", 100)), "expires": time.time() + ttl, "img": img}


_preset_cache: dict[str, bytes] = {}


def preset_gif(name: str) -> bytes:
    if name not in _preset_cache:
        _preset_cache[name] = skins.fit(skins.PRESETS[name]())
    return _preset_cache[name]


def giphy(q: str) -> list[dict]:
    key = state.cfg["giphy_key"]
    if not key:
        raise ValueError("add a GIPHY API key first")
    params = {"api_key": key, "limit": 24, "rating": "g"}
    endpoint = "search" if q else "trending"
    if q:
        params["q"] = q[:100]
    url = f"https://api.giphy.com/v1/gifs/{endpoint}?{urllib.parse.urlencode(params)}"
    data = json.loads(urllib.request.urlopen(url, timeout=10).read())["data"]
    return [{"id": g["id"], "title": g.get("title", ""),
             "thumb": g["images"]["fixed_width_small"]["url"],
             "url": (g["images"].get("downsized") or g["images"]["original"])["url"]} for g in data]


def save_gif(body: dict) -> str:
    if body.get("preset"):
        name = str(body["preset"])
        if name not in skins.PRESETS:
            raise ValueError("unknown preset")
        data, body = preset_gif(name), {"name": name}
    elif body.get("url"):
        url = str(body["url"])
        if not url.startswith(("https://", "http://")):
            raise ValueError("url must be http(s)")
        req = urllib.request.Request(url, headers={"User-Agent": "idotmatrix-daemon"})
        data = urllib.request.urlopen(req, timeout=20).read(8_000_001)
        if len(data) > 8_000_000:
            raise ValueError("gif larger than 8MB")
    else:
        data = base64.b64decode(body["data"])
    frames = skins.normalize_gif(data)
    base = re.sub(r"[^a-z0-9_-]+", "-", str(body.get("name") or "gif").lower().rsplit(".", 1)[0]).strip("-")[:30] or "gif"
    name, i = f"{base}.gif", 1
    while (GIF_DIR / name).exists():
        i += 1
        name = f"{base}-{i}.gif"
    GIF_DIR.mkdir(parents=True, exist_ok=True)
    (GIF_DIR / name).write_bytes(skins.to_gif([f for f, _ in frames], [d for _, d in frames]))
    return name


class Handler(BaseHTTPRequestHandler):
    loop: asyncio.AbstractEventLoop

    def _send(self, code: int, body: bytes = b"", ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode())

    def _trusted(self) -> bool:
        # DNS-rebinding guard: only answer requests addressed to us by loopback name
        return self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def do_GET(self):
        if not self._trusted():
            return self._json(403, {"error": "bad host"})
        path = self.path.split("?")[0]
        if path == "/":
            return self._send(200, UI_FILE.read_bytes(), "text/html; charset=utf-8")
        if path == "/preview":
            ctype, body = state.preview
            return self._send(200, body, ctype)
        if path == "/config":
            return self._json(200, {**state.cfg, "giphy_key": bool(state.cfg["giphy_key"])})  # never echo the key
        if path == "/presets":
            return self._json(200, list(skins.PRESETS))
        if path == "/cat/view":  # the real cat, live, for petting in the web UI
            buf = io.BytesIO()
            state.cat.frame(time.time(), state.cat_ctx()).save(buf, format="PNG")
            return self._send(200, buf.getvalue(), "image/png")
        if path == "/cat/tricks":
            return self._json(200, cat.TRICK_LABELS)
        if path == "/markets":
            return self._json(200, markets.NAMES)
        if path == "/vis_styles":
            return self._json(200, skins.Visualizer.STYLES)
        if path == "/games":
            return self._json(200, [{"id": k, "title": g.title, "help": g.help, "action": g.action} for k, g in game.GAMES.items()])
        if path == "/layouts":
            return self._json(200, render.LAYOUTS)
        if path == "/modules":
            return self._json(200, [{"id": k, "label": v["label"], "font": v["font"], "color": v["color"],
                                     "single": k not in ("divider", "spacer", "progress")}
                                    for k, v in render.MODULES.items()])
        if path.startswith("/presets/") and path[9:-4] in skins.PRESETS and path.endswith(".gif"):
            return self._send(200, preset_gif(path[9:-4]), "image/gif")
        if path == "/giphy":
            try:
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("q", [""])[0]
                return self._json(200, giphy(q.strip()))
            except Exception as e:
                return self._json(400, {"error": str(e)})
        if path == "/gifs":
            names = sorted(GIF_DIR.glob("*.gif"), key=lambda p: -p.stat().st_mtime) if GIF_DIR.exists() else []
            return self._json(200, [p.name for p in names])
        if path.startswith("/gifs/") and GIF_NAME.match(path[6:]) and (GIF_DIR / path[6:]).exists():
            return self._send(200, (GIF_DIR / path[6:]).read_bytes(), "image/gif")
        if path == "/status":
            now, m = time.time(), state.music
            return self._json(200, {
                "connected": state.connected, "showing": state.current, "paired": bool(state.address) or FAKE,
                "fake": FAKE, "version": __version__, "service": SERVICE, "service_installed": system.service_installed(),
                "preview_crc": zlib.crc32(state.preview[1]), "skin": state.cfg["skin"],
                "secs_since_ack": round(time.monotonic() - state.last_ack),
                "weather": state.weather, "city": state.cfg["city"],
                "music": m and {k: m[k] for k in ("title", "artist", "album")} | {"art": m["art"] is not None},
                "sessions": {k[:8]: {"state": v["state"], "cwd": v["cwd"], "age": round(now - v["at"])}
                             for k, v in list(state.sessions.items())},
                "scenes": {k: {"ttl": round(v["expires"] - now)} for k, v in list(state.scenes.items())},
                "video": (v := state.video) and {"title": v.title, "pos": round(v.pos / video.FPS),
                                                 "len": round(len(v.frames) / video.FPS), "decoding": not v.done},
                "video_error": state.video_error,
                "timer": (tm := state.timer) and {"remaining": max(0, round(tm["end"] - now)), "total": tm["total"],
                                                  "label": tm["label"]},
                "idle": round(state.idle), "cat_mood": state.cat.mood,
                "cat": {**state.cat.state(), "wants": state.cat.wants(),
                        "doing": state.cat.trick[0] if state.cat.busy(now) else None},
                "mic": state.mic.live,
                "game": state.game and {"title": state.game.title, "score": state.game.score, "over": state.game.over},
            })
        self._json(404, {"error": "not found"})

    def do_POST(self):
        # JSON content-type forces a CORS preflight, so other web pages can't drive this API
        if not self._trusted() or not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._json(403, {"error": "forbidden"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_BODY:
                return self._json(413, {"error": "too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/event":
                self.loop.call_soon_threadsafe(state.event, body)
                return self._send(204)  # empty body: Claude Code treats it as a no-op hook
            if self.path == "/cat":  # {"do": trick} | {"pet": head|chin|belly} | {"talk": listen|speak|done, "env"?}
                now = time.time()
                if "talk" in body:
                    did, dur = str(body["talk"]), state.cat.talk(str(body["talk"]), now, body.get("env"))
                elif "pet" in body:
                    did, dur = state.cat.pet(str(body["pet"]), now)
                else:
                    did, dur = str(body.get("do")), state.cat.do(str(body.get("do")), now)
                state.cat_until = max(state.cat_until, now + dur)
                return self._json(200, {"ok": True, "did": did, "secs": dur, "needs": state.cat.state()["needs"]})
            if self.path == "/setup/scan":  # first-run pairing from the web UI
                found = asyncio.run_coroutine_threadsafe(device.scan(6), self.loop).result(20)
                return self._json(200, [{"address": a, "name": n} for a, n in found])
            if self.path == "/setup/pair":
                addr = str(body.get("address", "")).strip()
                if not re.fullmatch(r"[0-9A-Fa-f:-]{12,40}", addr):
                    raise ValueError("bad address")
                device.save_address(addr)
                state.address = addr
                return self._json(200, {"ok": True})
            if self.path == "/service":  # run in the background (start at login) or stop doing so
                threading.Thread(target=handover if body.get("on") else system.service_uninstall, daemon=True).start()
                return self._json(200, {"ok": True})
            if self.path == "/mic":  # levels from the web UI's microphone
                state.mic.update(body.get("bands"), body.get("rms", 0))
                return self._send(204)
            if self.path == "/timer":
                if body.get("stop"):
                    state.timer = None
                elif body.get("add") and state.timer:
                    add = int(body["add"])
                    state.timer = {**state.timer, "end": state.timer["end"] + add, "total": state.timer["total"] + add}
                else:
                    secs = int(body.get("secs", 0))
                    if not 1 <= secs <= 24 * 3600:
                        raise ValueError("secs: 1 to 86400")
                    state.timer = {"end": time.time() + secs, "total": secs, "label": str(body.get("label", ""))[:20]}
                return self._json(200, {"ok": True})
            if self.path == "/video":
                if body.get("stop"):
                    old, state.video = state.video, None
                    old and old.stop()
                    return self._json(200, {"ok": True})
                if body.get("data"):  # uploaded file
                    ext = re.sub(r"[^a-z0-9]", "", Path(str(body.get("name", ""))).suffix.lower())[:5] or "mp4"
                    src, title = HOME / f"upload.{ext}", Path(str(body.get("name", "video"))).stem[:60]
                    src.write_bytes(base64.b64decode(body["data"]))
                    src = str(src)
                else:
                    url = str(body.get("url", "")).strip()
                    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
                        raise ValueError("need an http(s) link")
                    src, title = video.stream_url(url)
                player = video.Player(src, title, fill=body.get("fill", True) is not False)
                old, state.video, state.video_error, state.game = state.video, player, None, None
                old and old.stop()
                return self._json(200, {"ok": True, "title": title})
            if self.path == "/game":
                act = body.get("action")
                if act == "start":
                    cls = game.GAMES.get(body.get("name") or state.cfg["game"])
                    if not cls:
                        return self._json(400, {"error": "unknown game"})
                    self.loop.call_soon_threadsafe(setattr, state, "game", cls())
                    if state.video:  # one live thing at a time
                        state.video.stop()
                        self.loop.call_soon_threadsafe(setattr, state, "video", None)
                elif act == "stop":
                    self.loop.call_soon_threadsafe(setattr, state, "game", None)
                elif act == "key" and state.game:
                    self.loop.call_soon_threadsafe(state.game.key, str(body.get("dir")))
                else:
                    return self._json(400, {"error": "action: start | stop | key"})
                return self._json(200, {"ok": True})
            if self.path == "/scene":
                if body.get("clear"):
                    sid = str(body.get("id", "scene"))
                    self.loop.call_soon_threadsafe(state.scenes.pop, sid, None)
                else:
                    sid, scene = parse_scene(body)
                    self.loop.call_soon_threadsafe(state.scenes.__setitem__, sid, scene)
                return self._json(200, {"ok": True, "id": sid})
            if self.path == "/render":
                draft = validated(state.cfg, {k: v for k, v in body.items() if k not in ("city", "giphy_key", "thumb")})
                if draft["skin"] == "karaoke" and not body.get("thumb"):
                    state.lyrics_wanted = time.time()
                if draft["skin"] == "markets" and not body.get("thumb"):  # previewing it: fetch quotes now
                    state.want_markets(draft["markets"], draft["markets_vs"])
                _, kind, payload = state.output(draft)
                if kind == "gif":
                    return self._send(200, payload[1], "image/gif")
                buf = io.BytesIO()
                payload.save(buf, format="PNG")
                return self._send(200, buf.getvalue(), "image/png")
            if self.path == "/config":
                new = validated(state.cfg, body)
                city_changed = new["city"] != state.cfg["city"]
                device.set_gamma(new["gamma"])
                state.cfg = new
                CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                CONFIG_FILE.write_text(json.dumps(new, indent=2))
                if city_changed and state.weather_wake:
                    self.loop.call_soon_threadsafe(state.weather_wake.set)
                return self._json(200, {**new, "giphy_key": bool(new["giphy_key"])})
            if self.path == "/gifs":
                return self._json(200, {"name": save_gif(body)})
            if self.path == "/gifs/delete":
                name = str(body.get("name", ""))
                if GIF_NAME.match(name):
                    (GIF_DIR / name).unlink(missing_ok=True)
                    if state.cfg["gif"] == name:
                        state.cfg = {**state.cfg, "gif": None}
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "not found"})
        except Exception as e:
            self._json(400, {"error": str(e)})

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)


async def weather_loop() -> None:
    state.weather_wake = asyncio.Event()
    while True:
        cfg = state.cfg
        if cfg["lat"] is None:  # no city yet: weather stays hidden until one is set in Settings
            await state.weather_wake.wait()
            state.weather_wake.clear()
            continue
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={cfg['lat']}&longitude={cfg['lon']}"
               "&current=temperature_2m,weather_code,is_day&hourly=temperature_2m&forecast_hours=12"
               "&daily=sunrise,sunset&forecast_days=2&timezone=auto")
        wait = WEATHER_EVERY
        try:
            raw = await asyncio.to_thread(lambda: urllib.request.urlopen(url, timeout=15).read())
            d = json.loads(raw)
            cur = d["current"]
            state.weather = {"temp": cur["temperature_2m"], "code": cur["weather_code"],
                             "is_day": bool(cur["is_day"]), "at": time.time(),
                             "hourly": d.get("hourly", {}).get("temperature_2m", []),
                             "sun": {"rise": d.get("daily", {}).get("sunrise", []),
                                     "set": d.get("daily", {}).get("sunset", [])}}
            log.info("weather %s %s°", cfg["city"], state.weather["temp"])
            try:
                state.weather["pm25"] = await asyncio.to_thread(air_pm25, cfg["lat"], cfg["lon"])
            except Exception as e:
                log.warning("air quality fetch failed: %s", e)
        except Exception as e:
            log.warning("weather fetch failed: %s", e)
            wait = 60
        try:
            await asyncio.wait_for(state.weather_wake.wait(), wait)
        except TimeoutError:
            pass
        state.weather_wake.clear()


async def markets_loop() -> None:
    """Quotes for the markets skin, only while it's applied or being previewed (no calls otherwise)."""
    state.markets_wake = asyncio.Event()
    fetched: dict[tuple[str, str], float] = {}  # (id, compare-with) -> when
    retry_at = 0.0
    while True:
        cfg, now = state.cfg, time.time()
        wants = [state.markets_draft] if now - state.markets_wanted < 120 else []
        if cfg["skin"] == "markets":
            wants.append((cfg["markets"], cfg["markets_vs"]))
        for items, vs in wants if now >= retry_at else []:
            due = [i for i in items if now - fetched.get((i, vs), 0) > MARKETS_EVERY]
            if not due:
                continue
            try:
                got = await asyncio.to_thread(markets.fetch, due, vs)
                state.quotes.update({(i, vs): q for i, q in got.items()})
                fetched.update({(i, vs): now for i in due})
                log.info("markets: %d of %d quotes (vs %s)", len(got), len(due), vs)
            except Exception as e:
                log.warning("markets fetch failed: %s", e)
                retry_at = now + 60  # previews keep waking us; don't hammer a failing source
                break
        try:
            await asyncio.wait_for(state.markets_wake.wait(), 30)
        except TimeoutError:
            pass
        state.markets_wake.clear()


async def idle_loop() -> None:
    """Seconds since keyboard/mouse input (no permission needed); the cat naps when you're away."""
    saved, n = None, -1
    while True:
        n += 1
        try:
            idle = await asyncio.to_thread(system.idle_seconds)
            state.idle = idle if idle is not None else 0.0
        except Exception as e:
            log.debug("idle: %s", e)
        if n % 30 == 0:  # every minute: needs drift even when the cat isn't on screen; save them
            state.cat.tick(time.time(), state.cat.mood in ("sleep", "tired") or state.cat.napping)
            if (cur := json.dumps(state.cat.state()["needs"])) != saved:
                try:
                    CAT_FILE.write_text(json.dumps(state.cat.state()))
                    saved = cur
                except OSError as e:
                    log.warning("couldn't save the cat: %s", e)
        await asyncio.sleep(2)


async def music_loop() -> None:
    """Whatever the OS reports as now playing (any app): media-control / playerctl / Windows media session."""
    if hint := system.now_playing_source():
        log.warning("now playing disabled: %s", hint)
        return
    lyrics_retry = 0.0
    while True:
        try:
            d = await asyncio.to_thread(system.now_playing)
            if d:
                key = f"{d['title']}|{d['artist']}|{d['album']}"
                if not state.music or state.music["key"] != key:
                    art = Image.open(io.BytesIO(d["art"])).convert("RGB") if d["art"] else None
                    state.last_art = art or state.last_art
                    state.music = {**d, "art": art, "key": key, "at": time.time()}
                    log.info("now playing %s", key)
                else:  # same track: just the position, which moves on every poll (and on seeks)
                    state.music = {**state.music, "pos": d.get("pos"), "at": time.time()}
            else:
                state.music = None
        except Exception as e:
            log.debug("now playing: %s", e)
        m, now = state.music, time.time()
        if (m and state.lyrics[0] != m["key"] and now >= lyrics_retry
                and (state.cfg["skin"] == "karaoke" or now - state.lyrics_wanted < 120)):
            try:  # only while the karaoke skin is in use: the title and artist go to lrclib.net
                lines = await asyncio.to_thread(lyrics.fetch, m["title"], m["artist"], m["album"], m.get("duration"))
                state.lyrics = (m["key"], lines)
                log.info("lyrics: %d lines for %s", len(lines), m["title"])
            except Exception as e:
                log.warning("lyrics fetch failed: %s", e)
                lyrics_retry = now + 60
        await asyncio.sleep(MUSIC_POLL)


async def display_loop(fake: bool) -> None:
    dev, last_sig, last_send, misses, backoff, level, live = None, None, 0.0, 0, 2, None, False
    while True:
        want = "fake" if fake else state.address
        if not want:  # not paired yet: the web UI scans and picks
            state.connected, state.last_ack = False, time.monotonic()
            await asyncio.sleep(1)
            continue
        if dev is None or dev.address != want:
            if dev:
                await dev.disconnect()
            dev = device.FakeDevice() if fake else device.Device(want)
        if time.monotonic() - state.last_ack > HARD_DEADLINE:
            log.error("no ack for %ds, exiting so the service manager restarts us", HARD_DEADLINE)
            os._exit(1)
        if not dev.connected:
            state.connected = False
            try:
                await dev.connect()
                state.connected, last_sig, misses, backoff, level = True, None, 0, 2, None
                state.last_ack = time.monotonic()
            except Exception as e:
                log.warning("connect failed (%s), retry in %ds", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
        try:
            state.current, kind, payload = state.output()
            if kind == "frame":
                buf = io.BytesIO()
                payload.save(buf, format="PNG")
                state.preview = ("image/png", buf.getvalue())
                png = device.encode(payload, photo=state.current in ("album", "video"))
                sig, send = png, lambda: dev.show_png(png)
            else:
                key, preview_gif, dev_gif = payload
                state.preview = ("image/gif", preview_gif)
                sig, send = key, lambda: dev.show_gif(dev_gif)
            now = time.monotonic()
            ok = None
            live = state.game or state.video or state.current in ("visualizer", "cat", "timer", "karaoke")  # ~35ms per frame, so these skip the 1s limit
            if sig != last_sig and now - last_send >= (0 if live else MIN_SEND_GAP):
                ok = await asyncio.wait_for(send(), 30)
                if live:
                    log.debug("live frame sent in %.0fms", (time.monotonic() - now) * 1000)
                last_send = now
                if ok:
                    last_sig = sig
            elif level != state.cfg["brightness"]:
                ok = await asyncio.wait_for(dev.brightness(state.cfg["brightness"]), 10)
                last_send = now
                if ok:
                    level = state.cfg["brightness"]
            elif now - last_send >= HEARTBEAT:
                ok = await asyncio.wait_for(dev.ping(), 10)
                last_send = now
            if ok is True:
                misses, state.last_ack = 0, time.monotonic()
            elif ok is False:
                misses += 1
                log.warning("no ack (%d/%d)", misses, MAX_MISSES)
                if misses >= MAX_MISSES:
                    log.warning("display unresponsive, reconnecting")
                    await dev.disconnect()
        except Exception as e:
            log.warning("send failed: %r", e)
            await dev.disconnect()
        await asyncio.sleep(0.02 if live else 0.25)


FAKE = False
SERVICE = False  # this copy was started by the service manager
SERVER: ThreadingHTTPServer | None = None


def handover() -> None:
    """Foreground copy → background service: free the port (and, on exit, the Bluetooth link), install, quit."""
    time.sleep(0.3)  # let the HTTP reply go out
    SERVER.shutdown()
    SERVER.server_close()
    try:
        log.info("now running in the background: %s", system.service_install())
    finally:
        os._exit(0)


async def main(port: int = PORT, fake: bool = False, open_browser: bool = False, log_file: str | None = None,
               service: bool = False) -> None:
    global PORT, FAKE, SERVICE, SERVER
    PORT, FAKE, SERVICE = port, fake, service
    handlers = [logging.StreamHandler()] + ([logging.FileHandler(log_file)] if log_file else [])
    logging.basicConfig(force=True, level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=handlers)
    logging.getLogger("bleak").setLevel(logging.WARNING)
    Handler.loop = asyncio.get_running_loop()
    try:
        server = SERVER = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        raise SystemExit(f"port {PORT} is busy: is dotmatrix already running? (try `dotmatrix status`)")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{PORT}"
    log.info("web ui on %s%s", url, " (fake device)" if fake else "")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    state.loop = asyncio.get_running_loop()
    await asyncio.gather(weather_loop(), music_loop(), idle_loop(), markets_loop(), display_loop(fake))
