"""Video on the panel: ffmpeg decodes any file/stream to 32x32 RGB at FPS; the daemon streams frames live
(a BLE frame takes ~35ms). Links go through yt-dlp first (YouTube etc.). No audio, it's an LED panel."""
import subprocess
import threading
import time

from PIL import Image

from . import system

FPS = 12
MAX_SECS = 600
FRAME = 32 * 32 * 3


def _tool(name: str) -> str:
    found = system.tool(name)
    if not found:
        raise RuntimeError(f"{name} not installed")
    return found


def stream_url(url: str) -> tuple[str, str]:
    """Page link -> (direct media URL, title). Asks for a small rendition; we only need 32px."""
    out = subprocess.run([_tool("yt-dlp"), "-f", "bv*/b", "-S", "+res,+size",
                          "--no-playlist", "-g", "--get-title", "--", url],
                         capture_output=True, text=True, timeout=60)
    lines = out.stdout.strip().splitlines()
    if out.returncode or len(lines) < 2:
        raise RuntimeError((out.stderr.strip().splitlines() or ["yt-dlp failed"])[-1][:200])
    return lines[1], lines[0]


class Player:
    """Decodes in a background thread; playback starts with the first frames and loops once done."""

    def __init__(self, src: str, title: str, fill: bool = True):
        self.title, self.frames, self.done, self.error = title, [], False, None
        self.start = time.monotonic()
        fit = ("scale=32:32:force_original_aspect_ratio=increase:flags=area,crop=32:32" if fill else
               "scale=32:32:force_original_aspect_ratio=decrease:flags=area,pad=32:32:(ow-iw)/2:(oh-ih)/2")
        self.proc = subprocess.Popen(
            [_tool("ffmpeg"), "-v", "error", "-nostdin", "-i", src, "-t", str(MAX_SECS),
             "-vf", f"fps={FPS},{fit}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while chunk := self.proc.stdout.read(FRAME):
            if len(chunk) == FRAME:
                self.frames.append(chunk)
        self.proc.wait()
        if not self.frames:
            self.error = (self.proc.stderr.read().decode(errors="replace").strip().splitlines() or ["no frames"])[-1][:200]
        self.done = True

    def stop(self):
        if self.proc.poll() is None:
            self.proc.kill()

    @property
    def pos(self) -> int:
        """Frame index for now: real time, waits at the decode edge, loops once fully decoded."""
        i = int((time.monotonic() - self.start) * FPS)
        if self.done and self.frames:
            return i % len(self.frames)
        if i >= len(self.frames):  # decoder behind: hold the clock so we don't skip ahead
            self.start = time.monotonic() - max(0, len(self.frames) - 1) / FPS
            return max(0, len(self.frames) - 1)
        return i

    def frame(self) -> Image.Image | None:
        return Image.frombytes("RGB", (32, 32), self.frames[self.pos]) if self.frames else None


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:  # 2s synthetic clip: red then blue
        clip = f"{d}/t.mp4"
        subprocess.run([_tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "color=red:s=64x48:d=1:r=24",
                        "-f", "lavfi", "-i", "color=blue:s=64x48:d=1:r=24", "-filter_complex", "[0][1]concat=n=2",
                        clip], check=True)
        p = Player(clip, "test")
        while not p.done:
            time.sleep(0.05)
        assert p.error is None and len(p.frames) == 2 * FPS, len(p.frames)
        assert p.frame().size == (32, 32)
        r, b = Image.frombytes("RGB", (32, 32), p.frames[0]), Image.frombytes("RGB", (32, 32), p.frames[-1])
        assert r.getpixel((16, 16))[0] > 200 and b.getpixel((16, 16))[2] > 200
        bad = Player(f"{d}/missing.mp4", "x")
        while not bad.done:
            time.sleep(0.05)
        assert bad.error and bad.frame() is None
    print("ok")
