# dotmatrix-unlocked

[![ci](https://github.com/anishsrinivasan/dotmatrix-unlocked/actions/workflows/ci.yml/badge.svg)](https://github.com/anishsrinivasan/dotmatrix-unlocked/actions/workflows/ci.yml)

Turn a cheap iDotMatrix-compatible **32×32 Bluetooth LED panel** into a desk companion, run from your computer
with a local web UI.

![The web UI: a live preview of the panel next to skins and dashboard modules](https://raw.githubusercontent.com/anishsrinivasan/dotmatrix-unlocked/main/docs/display.png)

## Features

**Display: pick it, preview it, Apply.** Nothing reaches the panel until you press Apply.
- **Dashboard** with 17 modules: clock (big, analog or binary), weather, 8-hour forecast, sunrise/sunset, moon
  phase, air quality (PM2.5, Indian cities), week, month, day progress, now playing, and live **Claude Code** activity.
- 12 ready-made screens (Classic, Big clock, Weather station, Night owl, Calendar, Claude ops…). Reorder modules,
  pick fonts and colours, then save your own layouts.
- **Skins:** album art, a spinning vinyl, GIFs, a Winamp-style **visualizer** (7 styles), a mischievous pixel
  **cat**, **Karaoke**, and **Markets**.
- **Markets:** pick what to track: gold (24K/22K per gram), silver per kg, the rupee against USD, EUR, GBP, AED,
  SGD and JPY, Nifty 50, Nifty Bank, Brent, and any US stock ticker. Show the price, the change (+/−%), or both,
  since the previous close, a week or a month ago, or any date you pick. Free, no API keys.
- **Karaoke:** time-synced lyrics of whatever is playing (Spotify, Apple Music, YouTube in a browser…), filling in
  colour as they're sung, from [LRCLIB](https://lrclib.net). Tamil, Hindi and other Indian scripts are romanised.
  Free, no login; a timing slider fixes lines that run late.
- **GIF library:** 16 built-in animations, GIPHY search, or upload your own. GIFs are re-tuned for LEDs, with
  sharper shrinking, a contrast stretch and no dither noise.

**Live: takes over the panel right away. Stop it and your skin comes back.**
- **Games:** Snake, Tetris, Breakout, 2048 and Flappy, played with the keyboard or on-screen buttons.
- **Video:** YouTube links or uploaded clips (experimental).
- **Countdown timer** that shows over any skin, plus quick text or image messages.

**It reacts to you**
- The cat naps when you're idle, waves when Claude Code needs your input, and dances to your music. Ask it to do
  a flip, feed it, or have it catch a fish.
- The microphone (off by default, runs in your browser) drives the visualizer, and a clap startles the cat.
- Claude Code hooks show when sessions are working or waiting on you, and can pull the dashboard up when Claude
  needs input.

**Settings**
- Brightness, gamma (to calibrate your LEDs), weather city.
- **Run in the background:** start at login and restart after a crash, with a switch to turn it off.

| Markets | Live | Settings |
|---|---|---|
| ![Markets skin tracking gold, silver, the rupee and US stocks](https://raw.githubusercontent.com/anishsrinivasan/dotmatrix-unlocked/main/docs/markets.png) | ![Live view with Snake running](https://raw.githubusercontent.com/anishsrinivasan/dotmatrix-unlocked/main/docs/live.png) | ![Settings with the Run in the background switch](https://raw.githubusercontent.com/anishsrinivasan/dotmatrix-unlocked/main/docs/settings.png) |

> Not affiliated with iDotMatrix. Tested on a 32×32 `IDM-*` panel; other sizes aren't supported yet.

## Install

Needs Python 3.12+ and Bluetooth.

```sh
uv tool install dotmatrix-unlocked     # or: pipx install dotmatrix-unlocked
dotmatrix                              # opens http://127.0.0.1:7766; offers to keep running in the background
```

Don't have `uv`? See [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/), or use `pipx`.

In the web UI, click **Find my panel**. Turn the panel on first and close its phone app: the panel accepts only
one Bluetooth connection.

No panel? `dotmatrix run --fake` runs everything with the browser preview standing in for the display.

Then, optionally:

```sh
dotmatrix service install   # run in the background: start at login, restart if it crashes (also in Settings)
dotmatrix hooks install     # show Claude Code activity (edits ~/.claude/settings.json, keeps a .bak)
dotmatrix doctor            # checks everything and prints the fix for anything missing
```

To stop the background copy: turn off **Run in the background** in Settings, or `dotmatrix service uninstall`.

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
- Network calls: Open-Meteo for weather and snapdata.dev for air quality (only once you set a city); snapdata.dev
  and Yahoo Finance for Markets (only while that skin is in use); lrclib.net
  for Karaoke (the song's title and artist, only while that skin is in use); GIPHY if you add a key; and video links you paste.

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

## Changelog

See [CHANGELOG.md](CHANGELOG.md). Each GitHub release carries its section.

## License

GPL-3.0-or-later. It builds on [python3-idotmatrix-library](https://github.com/derkalle4/python3-idotmatrix-library),
which is also GPL-3.0.

Lyrics: [LRCLIB](https://lrclib.net), community-made. Market and air-quality data: [snapdata.dev](https://snapdata.dev) (IBJA, ECB, CPCB, EIA), and Yahoo Finance for US
stocks. Prices are for display only, not trading.
