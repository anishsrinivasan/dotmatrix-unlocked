# Changelog

All notable changes to dotmatrix-unlocked. Versions follow [semantic versioning](https://semver.org).

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
