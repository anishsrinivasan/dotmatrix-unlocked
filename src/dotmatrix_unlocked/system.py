"""Everything OS-specific lives here: config dir, external tools, now playing, idle time, background service.
Each probe returns None when the platform can't do it; callers degrade (no music row, cat never naps...)."""
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

APP = "dotmatrix-unlocked"
MAC, WIN, LINUX = sys.platform == "darwin", sys.platform == "win32", sys.platform.startswith("linux")


def config_dir() -> Path:
    if WIN:
        d = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP
    else:
        d = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP
    old = d.with_name("idotmatrix")  # pre-release name, same base dir: carry settings, GIFs and the paired panel over
    if not d.exists() and old.is_dir():
        shutil.copytree(old, d)
    d.mkdir(parents=True, exist_ok=True)
    return d


# services start with a bare PATH, so also look where package managers put things
EXTRA_DIRS = [Path.home() / ".local/bin", Path("/opt/homebrew/bin"), Path("/opt/homebrew/opt/ffmpeg-full/bin"),
              Path("/usr/local/bin"), Path("/usr/bin")]


def tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for d in EXTRA_DIRS:
        for cand in (d / name, d / f"{name}.exe"):
            if cand.exists():
                return str(cand)
    return None


def _run(args: list[str], timeout: float = 10) -> str | None:
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


# ---- now playing: {title, artist, album, art: bytes|None, pos: seconds|None, duration: seconds|None}
# or None when nothing is playing. pos is the play position right now (for synced lyrics).
def now_playing() -> dict | None:
    if MAC:
        return _np_mac()
    if LINUX:
        return _np_linux()
    if WIN:
        return _np_windows()
    return None


def now_playing_source() -> str | None:
    """What now_playing() needs, or None if it's available. For `doctor`."""
    if MAC and not tool("media-control"):
        return "brew install ungive/media-control/media-control"
    if LINUX and not tool("playerctl"):
        return "install playerctl (e.g. sudo apt install playerctl)"
    if WIN:
        try:
            import winrt.windows.media.control  # noqa: F401
        except ImportError:
            return 'pip install "winrt-Windows.Media.Control" "winrt-Windows.Foundation"'
    return None


def _np_mac():
    exe = tool("media-control")  # MediaRemote is gated since macOS 15.4; this helper still works
    out = exe and _run([exe, "get"])
    d = json.loads(out or "null") or {}
    if not (d.get("title") and d.get("playing")):
        return None
    art = base64.b64decode(d["artworkData"]) if d.get("artworkData") else None
    pos = d.get("elapsedTime")
    if pos is not None and d.get("timestamp"):  # elapsedTime was true at timestamp (whole seconds only)
        pos += (time.time() - datetime.fromisoformat(d["timestamp"]).timestamp()) * d.get("playbackRate", 1)
    return {"title": d["title"], "artist": d.get("artist", ""), "album": d.get("album", ""), "art": art,
            "pos": pos, "duration": d.get("duration")}


def _np_linux():
    exe = tool("playerctl")  # any MPRIS player: Spotify, browsers, VLC, mpv...
    out = exe and _run([exe, "metadata", "--format", "{{status}}\t{{title}}\t{{artist}}\t{{album}}\t{{mpris:artUrl}}\t{{position}}\t{{mpris:length}}"])
    if not out:
        return None
    status, title, artist, album, art_url, pos, length = (out.rstrip("\n").split("\t") + [""] * 7)[:7]
    if status != "Playing" or not title:
        return None
    art = None
    try:
        if art_url.startswith("file://"):
            art = Path(urllib.parse.unquote(art_url[7:])).read_bytes()
        elif art_url.startswith(("http://", "https://")):
            art = urllib.request.urlopen(art_url, timeout=5).read(2_000_000)
    except OSError:
        pass
    us = lambda v: int(v) / 1e6 if v.isdigit() else None  # MPRIS times are microseconds
    return {"title": title, "artist": artist, "album": album, "art": art, "pos": us(pos), "duration": us(length)}


def _np_windows():
    # ponytail: untested on real Windows; no album art yet (thumbnail stream needs more winrt plumbing)
    try:
        import asyncio
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
    except ImportError:
        return None

    async def get():
        session = (await Manager.request_async()).get_current_session()
        if not session or session.get_playback_info().playback_status != 4:  # 4 = Playing
            return None
        p = await session.try_get_media_properties_async()
        tl = session.get_timeline_properties()
        pos = tl.position.total_seconds() + (time.time() - tl.last_updated_time.timestamp())
        return {"title": p.title, "artist": p.artist, "album": p.album_title, "art": None,
                "pos": pos, "duration": tl.end_time.total_seconds() or None} if p.title else None
    return asyncio.run(get())


# ---- seconds since the last keyboard/mouse input, or None if unknown
def idle_seconds() -> float | None:
    if MAC:
        out = _run(["/usr/sbin/ioreg", "-c", "IOHIDSystem", "-d", "4"], timeout=5) or ""
        for line in out.splitlines():
            if '"HIDIdleTime"' in line:
                return int(line.rsplit("=", 1)[1]) / 1e9
        return None
    if WIN:
        import ctypes

        class LastInput(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        li = LastInput(ctypes.sizeof(LastInput), 0)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
            return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000
        return None
    if LINUX:  # X11 only; Wayland has no portable idle query
        exe = tool("xprintidle")
        out = exe and _run([exe], timeout=3)
        return int(out) / 1000 if out and out.strip().isdigit() else None
    return None


# ---- sleep/wake: before() runs (blocking, keep it short) just before the Mac sleeps, after() on wake
def on_sleep(before, after) -> bool:
    """macOS only (IOKit power notifications on their own run loop thread). False where unsupported.
    ponytail: Windows/Linux would need WM_POWERBROADCAST / logind; add if someone asks."""
    if not MAC:
        return False
    import ctypes
    import ctypes.util
    import threading
    iokit = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
    cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
    iokit.IORegisterForSystemPower.restype = ctypes.c_uint32
    iokit.IORegisterForSystemPower.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                                               ctypes.POINTER(ctypes.c_uint32)]
    iokit.IOAllowPowerChange.argtypes = [ctypes.c_uint32, ctypes.c_long]
    iokit.IONotificationPortGetRunLoopSource.restype = ctypes.c_void_p
    iokit.IONotificationPortGetRunLoopSource.argtypes = [ctypes.c_void_p]
    cf.CFRunLoopGetCurrent.restype = ctypes.c_void_p
    cf.CFRunLoopAddSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    can_sleep, will_sleep, powered_on = 0xE0000270, 0xE0000280, 0xE0000300
    root = ctypes.c_uint32(0)

    @ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p)
    def cb(_ref, _service, msg, arg):
        try:
            if msg == will_sleep:
                before()
            elif msg == powered_on:
                after()
        finally:
            if msg in (can_sleep, will_sleep):  # macOS waits up to 30s for this
                iokit.IOAllowPowerChange(root.value, arg or 0)

    def run():
        port, notifier = ctypes.c_void_p(), ctypes.c_uint32()
        root.value = iokit.IORegisterForSystemPower(None, ctypes.byref(port), cb, ctypes.byref(notifier))
        cf.CFRunLoopAddSource(cf.CFRunLoopGetCurrent(), iokit.IONotificationPortGetRunLoopSource(port),
                              ctypes.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode"))
        cf.CFRunLoopRun()

    on_sleep.cb = cb  # keep the C callback alive
    threading.Thread(target=run, daemon=True, name="power").start()
    return True


# ---- background service: start at login, restart on crash
LABEL = "io.github.dotmatrix-unlocked"


def _service_cmd(log_file: Path) -> list[str]:
    py = sys.executable
    if WIN and py.lower().endswith("python.exe"):
        py = py[:-10] + "pythonw.exe"  # no console window
    return [py, "-m", "dotmatrix_unlocked", "run", "--service", "--log-file", str(log_file)]


def service_file() -> Path | None:
    if MAC:
        return Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    if LINUX:
        return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd/user" / f"{APP}.service"
    return None


def service_install() -> str:
    log_file = config_dir() / "logs" / "daemon.log"
    log_file.parent.mkdir(exist_ok=True)
    cmd = _service_cmd(log_file)
    if MAC:
        f = service_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        args = "".join(f"<string>{a}</string>" for a in cmd)
        f.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key><array>{args}</array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
</dict></plist>
""")
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
        for _ in range(50):  # bootout returns before the old copy is gone; bootstrapping then fails with EIO
            if _run(["launchctl", "print", f"{domain}/{LABEL}"]) is None:
                break
            time.sleep(0.1)
        subprocess.run(["launchctl", "bootstrap", domain, str(f)], check=True)
        return f"launchd agent {f}"
    if LINUX:
        f = service_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"""[Unit]
Description=dotmatrix-unlocked: LED panel daemon
After=bluetooth.target

[Service]
ExecStart={" ".join(cmd)}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
""")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", f"{APP}.service"], check=True)
        return f"systemd user service {f} (headless? also run: loginctl enable-linger $USER)"
    if WIN:
        tr = subprocess.list2cmdline(cmd)
        subprocess.run(["schtasks", "/Create", "/TN", APP, "/TR", tr, "/SC", "ONLOGON", "/RL", "LIMITED", "/F"], check=True)
        subprocess.run(["schtasks", "/Run", "/TN", APP], check=True)
        return f"scheduled task '{APP}' (runs at logon)"
    raise SystemExit("unsupported platform")


def service_uninstall() -> str:
    if MAC:
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
        service_file().unlink(missing_ok=True)
    elif LINUX:
        subprocess.run(["systemctl", "--user", "disable", "--now", f"{APP}.service"], capture_output=True)
        service_file().unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    elif WIN:
        subprocess.run(["schtasks", "/End", "/TN", APP], capture_output=True)
        subprocess.run(["schtasks", "/Delete", "/TN", APP, "/F"], capture_output=True)
    return "removed"


def service_installed() -> bool:
    if WIN:
        return _run(["schtasks", "/Query", "/TN", APP]) is not None
    f = service_file()
    return bool(f and f.exists())


# ---- Claude Code hooks: merged into ~/.claude/settings.json, idempotent, with a backup
HOOK_EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest",
               "Notification", "Stop", "StopFailure", "SessionEnd"]


def _hook_command(port: int) -> str:
    if WIN:  # no POSIX shell guaranteed; a tiny python helper that always exits 0
        return subprocess.list2cmdline([sys.executable, "-m", "dotmatrix_unlocked", "--port", str(port), "hook"])
    # curl is ~10x faster to start than python, and this runs on every tool call; never blocks Claude
    return (f"curl -s -m 1 -H 'Content-Type: application/json' --data-binary @- "
            f"http://127.0.0.1:{port}/event >/dev/null 2>&1 || true")


def _is_ours(group: dict) -> bool:
    def ours(cmd: str) -> bool:
        return ("127.0.0.1" in cmd and "/event" in cmd) or ("dotmatrix_unlocked" in cmd and cmd.rstrip().endswith("hook"))
    return any(ours(h.get("command", "")) for h in group.get("hooks", []))


def hooks_install(port: int, settings: Path = Path.home() / ".claude" / "settings.json") -> str:
    data = json.loads(settings.read_text()) if settings.exists() else {}
    if settings.exists():
        settings.with_suffix(".json.bak").write_text(settings.read_text())
    hooks = data.setdefault("hooks", {})
    added = 0
    for ev in HOOK_EVENTS:
        groups = hooks.setdefault(ev, [])
        if any(_is_ours(g) for g in groups):
            continue
        groups.append({"hooks": [{"type": "command", "command": _hook_command(port), "timeout": 3}]})
        added += 1
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(data, indent=2) + "\n")
    return f"added {added} hook(s), {len(HOOK_EVENTS) - added} already there ({settings})"


def hooks_uninstall(settings: Path = Path.home() / ".claude" / "settings.json") -> str:
    if not settings.exists():
        return "no settings file"
    data = json.loads(settings.read_text())
    settings.with_suffix(".json.bak").write_text(settings.read_text())
    removed = 0
    for ev, groups in list(data.get("hooks", {}).items()):
        keep = [g for g in groups if not _is_ours(g)]
        removed += len(groups) - len(keep)
        if keep:
            data["hooks"][ev] = keep
        else:
            del data["hooks"][ev]
    settings.write_text(json.dumps(data, indent=2) + "\n")
    return f"removed {removed} hook(s)"


def hooks_installed(settings: Path = Path.home() / ".claude" / "settings.json") -> bool:
    try:
        hooks = json.loads(settings.read_text()).get("hooks", {})
    except (OSError, ValueError):
        return False
    return all(any(_is_ours(g) for g in hooks.get(ev, [])) for ev in HOOK_EVENTS)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        s = Path(d) / "settings.json"
        s.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "rtk thing"}]}]}}))
        assert "added 9" in hooks_install(7766, s) and hooks_installed(s)
        assert "added 0" in hooks_install(7766, s)  # idempotent
        assert len(json.loads(s.read_text())["hooks"]["Stop"]) == 2  # user's own hook kept
        assert "removed 9" in hooks_uninstall(s) and not hooks_installed(s)
        assert json.loads(s.read_text())["hooks"]["Stop"][0]["hooks"][0]["command"] == "rtk thing"
    assert config_dir().is_dir()
    assert _service_cmd(Path("/x"))[1:4] == ["-m", "dotmatrix_unlocked", "run"]
    assert _is_ours({"hooks": [{"command": 'C:\\py\\python.exe -m dotmatrix_unlocked --port 7766 hook'}]})
    print("ok", "idle", idle_seconds(), "np-missing", now_playing_source())
