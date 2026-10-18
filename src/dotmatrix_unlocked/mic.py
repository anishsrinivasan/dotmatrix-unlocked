"""Microphone levels pushed by the web UI (browser getUserMedia + Web Audio analyser -> POST /mic ~20x/s).
The daemon never opens the mic itself; when the page stops sending, everything falls back to synthetic."""
import time

BANDS = 16


class Mic:
    def __init__(self):
        self.bands, self.rms, self.updated, self.clap_at, self._avg = [0.0] * BANDS, 0.0, 0.0, 0.0, 0.01

    @property
    def live(self) -> bool:
        return time.monotonic() - self.updated < 1.0

    def update(self, bands: list, rms: float) -> None:
        if not isinstance(bands, list) or len(bands) != BANDS:
            raise ValueError(f"bands: list of {BANDS} numbers")
        self.bands = [max(0.0, min(1.0, float(b))) for b in bands]
        rms = max(0.0, min(1.0, float(rms)))
        if rms > 0.08 and rms > self._avg * 5:  # sudden loud spike vs the room's usual level = clap/bang
            self.clap_at = time.monotonic()
        self._avg = self._avg * 0.97 + rms * 0.03
        self.rms, self.updated = rms, time.monotonic()

    def clapped(self, within: float = 2.0) -> bool:
        return self.live and time.monotonic() - self.clap_at < within


if __name__ == "__main__":
    m = Mic()
    assert not m.live
    for _ in range(60):
        m.update([0.1] * BANDS, 0.002)  # quiet room
    assert m.live and not m.clapped()
    m.update([0.9] * BANDS, 0.5)  # bang
    assert m.clapped()
    m.update([2.0] + [-1.0] * 15, 0.01)
    assert m.bands[0] == 1.0 and m.bands[1] == 0.0  # clamped
    try:
        m.update([0.1] * 3, 0.1)
        raise AssertionError("short band list accepted")
    except ValueError:
        pass
    print("ok")
