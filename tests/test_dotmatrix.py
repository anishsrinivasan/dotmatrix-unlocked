"""Each module carries its own assert-based self-check; this runs them all, plus the whole app in --fake mode."""
import json
import os
import runpy
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

MODULES = ["render", "skins", "game", "cat", "mic", "system", "video", "markets", "lyrics"]


@pytest.mark.parametrize("module", MODULES)
def test_self_check(module, tmp_path, monkeypatch):
    if module == "video" and not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    runpy.run_module(f"dotmatrix_unlocked.{module}", run_name="__main__")


def test_fake_device_end_to_end(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path), "APPDATA": str(tmp_path)}
    proc = subprocess.Popen([sys.executable, "-m", "dotmatrix_unlocked", "--port", str(port), "run", "--fake", "--no-browser"],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"

    def call(path, body=None):
        req = urllib.request.Request(base + path, json.dumps(body).encode() if body is not None else None,
                                     {"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    try:
        for _ in range(50):
            try:
                status = json.loads(call("/status")[1])
                if status["connected"]:
                    break
            except OSError:
                pass
            time.sleep(0.2)
        assert status["fake"] and status["paired"] and status["connected"]
        assert call("/")[0] == 200
        code, png = call("/render", {"skin": "cat"})
        assert code == 200 and png[:4] == b"\x89PNG"
        call("/scene", {"id": "t", "text": "hi", "ttl": 5})
        for _ in range(30):
            if json.loads(call("/status")[1])["showing"] == "t":
                break
            time.sleep(0.2)
        assert json.loads(call("/status")[1])["showing"] == "t"
        assert call("/game", {"action": "start", "name": "tetris"})[0] == 200
        assert call("/game", {"action": "stop"})[0] == 200
        assert status["version"] and status["service"] is False

        # markets skin: registry, settings, validation, preview in every display mode
        names = json.loads(call("/markets")[1])
        assert {"GOLD", "SILVER", "USDINR", "EURINR", "JPYINR", "NIFTY"} <= names.keys()
        for show in ("price", "change", "both"):
            code, png = call("/render", {"skin": "markets", "markets": ["GOLD", "EURINR", "AAPL"], "markets_show": show,
                                         "markets_vs": "7d", "thumb": True})
            assert code == 200 and png[:4] == b"\x89PNG", show
        cfg = json.loads(call("/config", {"skin": "markets", "markets": ["gold", "msft"], "markets_vs": "2026-01-02",
                                          "markets_show": "change"})[1])
        assert cfg["markets"] == ["GOLD", "MSFT"] and cfg["markets_vs"] == "2026-01-02"
        for bad in ({"markets": ["AAPL; rm -rf"]}, {"markets_vs": "2999-01-01"}, {"markets_show": "loud"}):
            with pytest.raises(urllib.error.HTTPError) as e:
                call("/config", bad)
            assert e.value.code == 400, bad
        for _ in range(30):
            if json.loads(call("/status")[1])["showing"] == "markets":
                break
            time.sleep(0.2)
        assert json.loads(call("/status")[1])["showing"] == "markets"

        # karaoke: renders with or without music, timing knob is clamped and validated
        code, png = call("/render", {"skin": "karaoke"})
        assert code == 200 and png[:4] == b"\x89PNG"
        assert json.loads(call("/config", {"skin": "karaoke", "lyrics_offset": 9})[1])["lyrics_offset"] == 3.0
        with pytest.raises(urllib.error.HTTPError) as e:
            call("/config", {"lyrics_offset": "soon"})
        assert e.value.code == 400

        # air quality is a dashboard module like any other
        code, png = call("/render", {"skin": "dashboard", "layout": [{"id": "clock"}, {"id": "air"}]})
        assert code == 200 and png[:4] == b"\x89PNG"
    finally:
        proc.terminate()
        proc.wait(5)


def test_live_sources():
    """The free data sources still answer in the shape we parse. Skips when offline."""
    from dotmatrix_unlocked import markets
    import truststore
    truststore.inject_into_ssl()
    try:
        q = markets.fetch(["GOLD", "USDINR", "EURINR", "AAPL"], "7d")
    except OSError as e:
        pytest.skip(f"offline: {e}")
    assert {"GOLD", "USDINR", "EURINR"} <= q.keys(), q
    assert all(v > 0 and c is not None for k, (v, c) in q.items() if k != "AAPL"), q
    from dotmatrix_unlocked import lyrics
    lines = lyrics.fetch("Blinding Lights", "The Weeknd", "After Hours", 200)
    assert len(lines) > 20 and lines[0][0] > 0  # timed lines from lrclib.net
