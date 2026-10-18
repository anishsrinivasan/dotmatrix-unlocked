# dotmatrix-unlocked

[![ci](https://github.com/anishsrinivasan/dotmatrix-unlocked/actions/workflows/ci.yml/badge.svg)](https://github.com/anishsrinivasan/dotmatrix-unlocked/actions/workflows/ci.yml)

Turn a cheap iDotMatrix-compatible **32×32 Bluetooth LED panel** into a desk companion, run from your computer
with a local web UI.

- **Dashboard**: 16 modules (big, analog or binary clock, weather, 8-hour forecast, sunrise/sunset, moon phase,
  week, month, day progress, now playing, live **Claude Code** activity…). Start from 12 ready-made screens, or
  rearrange, restyle and save your own.
- **Skins**: album art, a spinning vinyl, any GIF (16 built-in animations, GIPHY, or your own: GIFs are
  re-tuned for LEDs with sharper shrinking, contrast stretch and no dither noise), a Winamp-style visualizer, and
  a mischievous pixel **cat** that reacts to what you're doing and does tricks on request.
- **Live**: Snake, Tetris, Breakout, 2048 and Flappy; YouTube or local video; a countdown timer; quick messages.
- Everything previews in the browser first and only goes to the panel when you press **Apply**.

> Not affiliated with iDotMatrix. Tested on a 32×32 `IDM-*` panel; other sizes aren't supported yet.

## Install

Needs Python 3.12+ and Bluetooth.

```sh
uv tool install git+https://github.com/anishsrinivasan/dotmatrix-unlocked
# or: pipx install git+https://github.com/anishsrinivasan/dotmatrix-unlocked
dotmatrix                              # starts it and opens http://127.0.0.1:7766
```

Don't have `uv`? See [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/), or use `pipx`.

In the web UI, click **Find my panel**. Turn the panel on first and close its phone app: the panel accepts only
one Bluetooth connection.

No panel? `dotmatrix run --fake` runs everything with the browser preview standing in for the display.

Then, optionally:

```sh
dotmatrix service install   # start at login, restart if it crashes
dotmatrix hooks install     # show Claude Code activity (edits ~/.claude/settings.json, keeps a .bak)
dotmatrix doctor            # checks everything and prints the fix for anything missing
```

## Platforms

| | macOS | Linux (incl. Raspberry Pi) | Windows |
|---|---|---|---|
| Panel over Bluetooth | ✓ | ✓ (BlueZ) | ✓ |
| Start at login | launchd | systemd user service | Task Scheduler |
| Now playing | [`media-control`](https://github.com/ungive/media-control) | `playerctl` (any MPRIS player) | built in (no album art yet) |
| Idle detection (the cat naps) | ✓ | X11 with `xprintidle` | ✓ |
| Video | `ffmpeg` + `yt-dlp` | same | same |

Windows support is new and less tested. Reports are welcome.

**macOS:** the first connection asks for Bluetooth permission for Python. If it was denied, enable it in
System Settings › Privacy & Security › Bluetooth.
**Raspberry Pi / headless Linux:** after `dotmatrix service install`, run `loginctl enable-linger $USER` so the
service starts without anyone logging in.

## Privacy

- The web UI and API listen on `127.0.0.1` only. Requests must come from that host and be JSON, so other
  websites can't drive your panel.
- The microphone (visualizer, clap-to-startle the cat) is **off by default**. It runs inside your browser, and
  only 16 loudness levels are sent to the local service; no audio leaves the browser.
- Network calls: Open-Meteo for weather (only once you set a city), GIPHY if you add a key, and video links
  you paste.

## Command line

```
dotmatrix                     start + open the web UI
dotmatrix run [--fake]        foreground
dotmatrix scene "HELLO" --ttl 10 --color 255,200,0
dotmatrix status
dotmatrix scan | hello | test | image PATH | brightness PCT   # direct to the panel, service stopped
```

The local HTTP API (`POST /scene`, `/event`, `/game`, `/timer`, `/cat`…) is what the web UI uses. Anything on
your machine can push to the panel with a `curl`.

## Development

```sh
git clone https://github.com/anishsrinivasan/dotmatrix-unlocked && cd dotmatrix-unlocked
uv sync --group dev
uv run pytest            # runs every module's self-check + the app end to end in --fake mode
uv run dotmatrix run --fake
```

- Add a **game**: subclass `Game` in `game.py` and add it to `GAMES`.
- Add a **dashboard module**: write a draw function and add it to `MODULES` in `render.py`.
- Add a **visualizer style** (`skins.py`) or a **cat trick** (`cat.py`): same idea.

The web UI picks all of these up automatically.

## License

GPL-3.0-or-later. It builds on [python3-idotmatrix-library](https://github.com/derkalle4/python3-idotmatrix-library),
which is also GPL-3.0.
