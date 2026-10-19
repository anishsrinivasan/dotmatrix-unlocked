# Changelog

All notable changes to dotmatrix-unlocked. Versions follow [semantic versioning](https://semver.org).

## 0.1.11 · 2026-10-20

### Changed
- Talking to the cat now gets real answers instead of an echo. Your browser turns what you say into text, an AI
  model on [OpenRouter](https://openrouter.ai) replies as the cat, and the browser says it in a squeaky voice while
  the cat's mouth moves on the panel. Ask for a trick ("do a flip", "want some fish?") and it does it after
  answering. It knows how it feels (hungry, bored, sleepy) and remembers the last few exchanges.
- Paste your OpenRouter key in the Cat card and pick any model (default `anthropic/claude-haiku-5.5`). The key is
  stored with your settings and never sent back to the browser. Without a key, or without speech recognition in
  your browser, it repeats you as before. `cat_ai_url` points it at any other OpenAI-compatible server.

## 0.1.10 · 2026-10-19

### Fixed
- The Cat preview showed a separate copy of the cat, so petting and talking only appeared on the panel and in the
  small live view. The preview now shows the same cat as the panel.
- The listening bubble's "?" was too pale to read on the panel.
- A custom `XDG_CONFIG_HOME` picked up settings from `~/.config/idotmatrix` (the pre-release name). Settings now
  carry over only from the same config folder.

## 0.1.9 · 2026-10-19

### Added
- **Talk to the cat**, Talking Tom style: turn it on in the Cat card and say something. The cat perks up its ears
  while you talk, then says it back in a squeaky voice through your computer's speakers, its mouth moving on the
  panel in time with the words. Your voice stays in the browser tab; only loudness levels reach the panel.

## 0.1.8 · 2026-10-19

### Added
- The cat has needs: food, energy, fun and love. They drift through the day (even while the app is closed) and are
  saved between restarts. When one runs low it asks for it: waits by its bowl ("FEED?"), wants to play ("PLAY?"),
  wants petting ("PET?"), or naps until it has its energy back.
- Pet the cat: stroke it with your mouse or finger on its live view in the Cat card. Head and chin get purrs and
  hearts; the belly is a trap until it trusts you (then belly rubs); too much petting earns a hiss and a swat.
- Treats fill it up (it refuses when full), games and tricks cheer it up and use up energy. Its needs show as bars
  in the Cat card, with what it wants right now.

## 0.1.7 · 2026-10-19

### Changed
- Karaoke looks like karaoke: every line has its own vibrant colour and fills in letter by letter as it's sung,
  upcoming lines show in a dim tint, and the lyrics glide up a row at a time instead of jumping a page.

### Fixed
- Tamil, Hindi, Telugu, Kannada, Malayalam, Bengali, Gujarati, Punjabi and Odia text showed blank on the panel.
  It's now romanised (ஒரு நாள் → ORU NAAL), in lyrics and in song titles on the dashboard.

## 0.1.6 · 2026-10-19

### Added
- **Karaoke** skin: time-synced lyrics of whatever is playing, the current line in white and the next one dimmed.
  Works with Spotify, Apple Music, browsers and anything else the OS reports as now playing. Lyrics come from
  LRCLIB (free, no key, no Spotify login), fetched only while the skin is in use. A **Timing** slider shifts lines
  up to 3 seconds either way.
- Now playing reports the play position on macOS, Linux and Windows.

## 0.1.5 · 2026-10-19

### Added
- Markets: rupee rates for EUR, GBP, AED, SGD and JPY, next to USD → ₹ (ECB rates, crossed through the dollar).
- Markets: **Show** price, change, or both (alternating on each page). Change mode puts an explicit + or − in front.
- Markets: **Change since** the previous close, 1 week ago, 1 month ago, or any past date. Weekends and holidays
  fall back to the last trading day before. Uses snapdata.dev's 30-day series and dated snapshots, and Yahoo's
  daily closes for US stocks.
- End-to-end tests for the Markets settings and the air module, and a live check that the free data sources still
  answer in the shape we parse.

### Fixed
- Weather, air quality, Markets and GIPHY failed with `CERTIFICATE_VERIFY_FAILED` on Python builds that ship
  without a certificate store (python.org's macOS installer). HTTPS now uses the operating system's trust store.
- A failing Markets source was retried about once a second while the preview was open. It now waits a minute.

## 0.1.4 · 2026-10-19

### Added
- **Markets** skin: track gold (24K/22K per gram), silver per kg, USD → ₹, Nifty 50, Nifty Bank, Brent and any US
  stock ticker. Green when it's up, red when it's down. Free, no API keys: snapdata.dev and Yahoo Finance.
  Fetched only while the skin is applied or being previewed.
- **Air** dashboard module: PM2.5 from the CPCB stations of the nearest Indian city to your weather location,
  coloured with India's AQI bands.

## 0.1.3 · 2026-10-19

### Added
- The web UI header shows the running version and a link to star the project on GitHub.
- `#display`, `#live` and `#settings` in the URL open that view directly.
- README screenshots and a full feature list.

## 0.1.2 · 2026-10-19

### Added
- Run in the background: `dotmatrix` offers to install the login service, and Settings has a
  **Run in the background** switch that hands the running copy over to it. Settings explains how to stop it.

### Fixed
- `dotmatrix service install` failed on macOS when the service was already running.

## 0.1.1 · 2026-10-19

### Added
- Published on PyPI: `uv tool install dotmatrix-unlocked`. Releases publish automatically from version tags.

## 0.1.0 · 2026-10-19

First public release: dashboard with 16 modules and 12 ready-made screens, album art, vinyl, GIFs, visualizer and
cat skins, games, video, countdown timer, Claude Code hooks, and setup on macOS, Linux and Windows.
