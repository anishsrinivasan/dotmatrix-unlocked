"""dotmatrix: drive an iDotMatrix-compatible 32x32 LED panel from your computer.

  dotmatrix                     start and open the web UI (pair your panel there)
  dotmatrix run [--fake]        run in the foreground; --fake needs no panel (the web preview is the display)
  dotmatrix service install     start at login and keep running (launchd / systemd / Task Scheduler)
  dotmatrix hooks install       show Claude Code activity on the panel
  dotmatrix doctor              check everything and say how to fix what's missing
Panel, direct (stop the service first): scan | hello | test | image PATH | brightness PCT
Via the running service: scene TEXT | clear ID | status"""
import argparse
import asyncio
import json
import logging
import os
import platform
import sys
import urllib.request

from . import system

PORT = int(os.environ.get("DOTMATRIX_PORT", "7766"))


def daemon_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def http(port: int, path: str, body: dict | None = None, timeout: float = 5) -> dict | None:
    req = urllib.request.Request(daemon_url(port) + path, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    return json.loads(raw) if raw else None


def running(port: int) -> dict | None:
    try:
        return http(port, "/status", timeout=2)
    except OSError:
        return None


def doctor(port: int) -> int:
    from . import device
    rows = []

    def check(ok: bool, what: str, fix: str = ""):
        rows.append(ok)
        print(f"  {'✓' if ok else '✗'} {what}" + ("" if ok or not fix else f"\n      → {fix}"))

    print(f"dotmatrix-unlocked · Python {platform.python_version()} · {platform.system()}")
    check(sys.version_info >= (3, 12), "Python 3.12+", "install a newer Python")
    if system.LINUX:
        out = system._run(["systemctl", "is-active", "bluetooth"]) or ""
        check(out.strip() == "active", "Bluetooth service running", "sudo systemctl enable --now bluetooth")
    st = running(port)
    check(bool(st), f"service answering on {daemon_url(port)}", "run `dotmatrix` or `dotmatrix service install`")
    addr = device.saved_address()
    check(bool(addr) or bool(st and st.get("fake")), "panel paired" + (f" ({addr})" if addr else ""),
          "open the web UI and click Find my panel (or `dotmatrix scan`)")
    if st and addr:
        check(st["connected"], "panel connected",
              "panel powered on? phone app closed? (only one Bluetooth connection at a time)"
              + (" macOS: allow Bluetooth for Python in System Settings › Privacy" if system.MAC else ""))
    check(system.service_installed(), "starts at login", "dotmatrix service install")
    hint = system.now_playing_source()
    check(hint is None, "now playing (music on the dashboard)", hint or "")
    check(system.idle_seconds() is not None, "idle time (the cat naps when you're away)",
          "install xprintidle (X11 only)" if system.LINUX else "")
    check(bool(system.tool("ffmpeg")), "ffmpeg (video)", "install ffmpeg")
    check(bool(system.tool("yt-dlp")), "yt-dlp (YouTube links)", "pip install yt-dlp")
    if (system.Path.home() / ".claude").exists():
        check(system.hooks_installed(), "Claude Code hooks", "dotmatrix hooks install")
    print(f"{sum(rows)}/{len(rows)} ok")
    return 0 if all(rows) else 1


async def direct(args) -> None:
    from PIL import Image
    from . import device, render
    if args.cmd == "scan":
        found = await device.scan()
        for addr, name in found:
            print(f"{name}  {addr}")
        if not found:
            print("no IDM-* panels found (powered on? phone app closed? Bluetooth permission for this terminal?)")
        elif len(found) == 1 or args.save:
            device.save_address(found[0][0])
            print(f"saved {found[0][0]}")
        return
    addr = args.address or device.saved_address()
    if not addr:
        raise SystemExit("no panel paired; run `dotmatrix scan` or pass --address")
    if running(args.port):
        raise SystemExit("the service holds the Bluetooth link; stop it first (or use the web UI)")
    dev = device.Device(addr)
    await dev.connect()
    try:
        if args.cmd == "hello":
            ok = await dev.show(render.hello())
        elif args.cmd == "test":
            ok = await dev.show(render.test_pattern())
        elif args.cmd == "image":
            ok = await dev.show(Image.open(args.path))
        else:
            ok = await dev.brightness(args.pct)
        print("acked" if ok else "sent (no ack)")
    finally:
        await dev.disconnect()


def hook(port: int) -> None:
    """Claude Code hook (Windows): forward the event, never fail, never block."""
    try:
        req = urllib.request.Request(daemon_url(port) + "/event", sys.stdin.buffer.read(),
                                     {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=1)
    except Exception:
        pass


def background(port: int) -> None:
    """Wait for the freshly installed service to answer, then open the web UI."""
    import time
    import webbrowser
    for _ in range(30):
        if running(port):
            print(f"running in the background → {daemon_url(port)}  (stop: `dotmatrix service uninstall`)")
            webbrowser.open(daemon_url(port))
            return
        time.sleep(0.5)
    print("installed, but it isn't answering yet; check `dotmatrix doctor`")


def main() -> None:
    import truststore
    truststore.inject_into_ssl()  # weather, markets, GIPHY: trust what the OS trusts
    p = argparse.ArgumentParser(prog="dotmatrix", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--address", help="panel Bluetooth address (default: the paired one)")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="run in the foreground")
    r.add_argument("--fake", action="store_true", help="no panel needed: the web preview is the display")
    r.add_argument("--no-browser", action="store_true")
    r.add_argument("--log-file")
    r.add_argument("--service", action="store_true", help=argparse.SUPPRESS)  # started by the service manager
    sv = sub.add_parser("service", help="start at login")
    sv.add_argument("action", choices=["install", "uninstall", "status"])
    hk = sub.add_parser("hooks", help="Claude Code integration")
    hk.add_argument("action", choices=["install", "uninstall"])
    sub.add_parser("hook", help=argparse.SUPPRESS)
    sub.add_parser("doctor", help="check setup")
    sub.add_parser("scan", help="find panels").add_argument("--save", action="store_true")
    sub.add_parser("hello")
    sub.add_parser("test", help="colour bars, to check orientation")
    sub.add_parser("image").add_argument("path")
    sub.add_parser("brightness").add_argument("pct", type=int)
    sc = sub.add_parser("scene", help="show text for a while")
    sc.add_argument("text")
    sc.add_argument("--ttl", type=float, default=10)
    sc.add_argument("--color", default="255,255,255")
    sc.add_argument("--priority", type=int, default=100)
    sc.add_argument("--id", default="cli")
    sub.add_parser("clear").add_argument("id")
    sub.add_parser("status")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    if args.cmd in (None, "run"):
        url = daemon_url(args.port)
        if args.cmd is None and running(args.port):  # already up (e.g. as a service): just open it
            import webbrowser
            print(f"already running → {url}")
            webbrowser.open(url)
            return
        if args.cmd is None and not system.service_installed() and sys.stdin.isatty():
            ans = input("Run in the background and start at login? Frees this terminal. [Y/n] ").strip().lower()
            if ans in ("", "y", "yes"):
                print(system.service_install())
                background(args.port)
                return
            print("Running here; Ctrl+C stops it. (Later: `dotmatrix service install`, or Settings in the web UI.)")
        from . import daemon
        service = getattr(args, "service", False)
        try:
            asyncio.run(daemon.main(args.port, fake=getattr(args, "fake", False),
                                    open_browser=args.cmd is None or not (args.no_browser or service),
                                    log_file=getattr(args, "log_file", None), service=service))
        except KeyboardInterrupt:
            pass
    elif args.cmd == "service":
        if args.action == "status":
            print("installed" if system.service_installed() else "not installed",
                  "· running" if running(args.port) else "· not running")
        elif args.action == "install":
            if running(args.port) and not running(args.port).get("service"):
                raise SystemExit("dotmatrix is running in a terminal; stop it (Ctrl+C) first, "
                                 "or turn on Run in the background in the web UI's Settings")
            print(system.service_install())
            background(args.port)
        else:
            print(system.service_uninstall())
    elif args.cmd == "hooks":
        print(system.hooks_install(args.port) if args.action == "install" else system.hooks_uninstall())
    elif args.cmd == "hook":
        hook(args.port)
    elif args.cmd == "doctor":
        raise SystemExit(doctor(args.port))
    elif args.cmd == "status":
        print(json.dumps(http(args.port, "/status"), indent=2))
    elif args.cmd == "scene":
        print(http(args.port, "/scene", {"id": args.id, "text": args.text, "ttl": args.ttl, "priority": args.priority,
                                         "color": [int(c) for c in args.color.split(",")]}))
    elif args.cmd == "clear":
        print(http(args.port, "/scene", {"id": args.id, "clear": True}))
    else:
        asyncio.run(direct(args))
