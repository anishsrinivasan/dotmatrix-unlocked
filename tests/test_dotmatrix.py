"""Each module carries its own assert-based self-check; this runs them all, plus the whole app in --fake mode."""
import json
import os
import runpy
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

MODULES = ["render", "skins", "game", "cat", "mic", "system", "video", "markets"]


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
    finally:
        proc.terminate()
        proc.wait(5)
