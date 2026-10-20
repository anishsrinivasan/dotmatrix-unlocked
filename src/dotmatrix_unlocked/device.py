"""Single BLE connection to an iDotMatrix display. Packet bytes come from the idotmatrix lib; pacing is ours."""
import asyncio
import io
import logging
import os

from bleak import BleakClient, BleakScanner
from idotmatrix.modules.gif import Gif as IdmGif
from idotmatrix.modules.image import Image as IdmImage
from PIL import Image

from . import system

WRITE_UUID = "0000fa02-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fa03-0000-1000-8000-00805f9b34fb"
# Firmware echoes every command as 05 00 <cmd> <sub> 01.
ACK_IMAGE = {bytes.fromhex(h) for h in ("0500010001", "0500000001", "0500010003")}  # next-block, image done, gif done
ACK_SCREEN_ON = {bytes.fromhex("0500070101")}
ACK_CLOCK = {bytes.fromhex("0500060101")}
ACK_BRIGHTNESS = {bytes.fromhex("0500048001")}
ADDRESS_FILE = system.config_dir() / "address"
ACK_TIMEOUT = 1.0  # firmware ack is flaky; fall back to ~1s pacing


def set_gamma(g: float) -> None:
    """LEDs are very non-linear (a 10% grey glows near full). Calibration knob: raise to darken mids."""
    global _LUT
    _LUT = [round(255 * (i / 255) ** g) for i in range(256)] * 3


# Photos/GIFs/video are already tone-mapped for screens; the drawn-UI gamma (often ~3 to keep dim greys dim)
# crushes their shadows to black. ponytail: one fixed curve; make it a setting if people ask.
PHOTO_GAMMA = float(os.environ.get("DOTMATRIX_PHOTO_GAMMA", "1.8"))
_PHOTO_LUT = [round(255 * (i / 255) ** PHOTO_GAMMA) for i in range(256)] * 3


set_gamma(float(os.environ.get("IDM_GAMMA", "2.2")))

log = logging.getLogger("device")


async def scan(timeout: float = 10.0) -> list[tuple[str, str]]:
    """Returns (address, name). On macOS address is a CoreBluetooth UUID, not a MAC."""
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    return [(d.address, a.local_name) for d, a in found.values() if (a.local_name or "").startswith("IDM-")]


def saved_address() -> str | None:
    return ADDRESS_FILE.read_text().strip() if ADDRESS_FILE.exists() else None


def save_address(address: str) -> None:
    ADDRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADDRESS_FILE.write_text(address)


def corrected(img: Image.Image, photo: bool = False) -> Image.Image:
    return img.convert("RGB").resize((32, 32), Image.NEAREST).point(_PHOTO_LUT if photo else _LUT)


def encode(img: Image.Image, photo: bool = False) -> bytes:
    buf = io.BytesIO()
    corrected(img, photo).save(buf, format="PNG")
    return buf.getvalue()


class Device:
    def __init__(self, address: str):
        self.address = address
        self.client: BleakClient | None = None
        self._expect: set[bytes] = set()
        self._ack = asyncio.Event()

    @property
    def connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    async def connect(self) -> None:
        # fresh client each time: reusing one after a firmware hang is unreliable
        self.client = BleakClient(self.address, disconnected_callback=lambda _: log.warning("disconnected"))
        await self.client.connect(timeout=20)
        await self.client.start_notify(NOTIFY_UUID, self._on_notify)
        log.info("connected to %s (mtu chunk %d)", self.address, self._chunk())

    async def disconnect(self) -> None:
        if self.client:
            try:
                await self.client.disconnect()
            except Exception as e:
                log.debug("disconnect: %s", e)

    def _on_notify(self, _char, data: bytearray) -> None:
        log.debug("notify %s", data.hex())
        if bytes(data) in self._expect:
            self._ack.set()

    def _chunk(self) -> int:
        return self.client.services.get_characteristic(WRITE_UUID).max_write_without_response_size

    async def send(self, data: bytes, expect: set[bytes] = frozenset()) -> bool:
        """Write-without-response in MTU-sized pieces; if expect is given, wait for one of those notifications."""
        self._expect, self._ack = set(expect), asyncio.Event()
        n = self._chunk()
        for i in range(0, len(data), n):
            await self.client.write_gatt_char(WRITE_UUID, data[i:i + n], response=False)
        if not expect:
            return True
        try:
            await asyncio.wait_for(self._ack.wait(), ACK_TIMEOUT)
            return True
        except TimeoutError:
            log.debug("no ack within %.1fs", ACK_TIMEOUT)
            return False

    async def show_png(self, png: bytes) -> bool:
        # ponytail: single 4096 block assumed; a 32x32 RGB PNG tops out ~3.1KB. Split+ack per block if that changes.
        assert len(png) <= 4096, len(png)
        await self.send(bytes([5, 0, 4, 1, 1]))  # DIY image mode
        return await self.send(IdmImage()._createPayloads(png), ACK_IMAGE)

    async def show_gif(self, gif: bytes) -> bool:
        """Device loops it natively. 4096-byte blocks, each waits for its ack (or ~1s) before the next."""
        await self.send(bytes([5, 0, 4, 1, 0]))  # leave DIY image mode, else the panel keeps the last still
        ok = True
        for block in IdmGif()._createPayloads(gif):
            ok = await self.send(bytes(block), ACK_IMAGE) and ok
        return ok

    async def show(self, img: Image.Image) -> bool:
        return await self.show_png(encode(img))

    async def ping(self) -> bool:
        return await self.send(bytes([5, 0, 7, 1, 1]), ACK_SCREEN_ON)  # screen on: harmless, always echoed

    async def own_clock(self, now, hour24: bool, rgb) -> bool:
        """Hand the panel to its built-in clock (set to now) so the time keeps moving while we can't send frames."""
        await self.send(bytes([5, 0, 4, 1, 0]))  # leave DIY image mode
        await self.send(bytes([11, 0, 1, 128, now.year % 100, now.month, now.day, now.isoweekday(),
                               now.hour, now.minute, now.second]))
        return await self.send(bytes([8, 0, 6, 1, 128 | (64 if hour24 else 0), *rgb]), ACK_CLOCK)

    async def brightness(self, pct: int) -> bool:
        return await self.send(bytes([5, 0, 4, 128, max(5, min(100, pct))]), ACK_BRIGHTNESS)


class FakeDevice(Device):
    """No Bluetooth: everything 'acks' instantly. The web preview is the display. For trying it out, dev, and CI."""

    def __init__(self, address: str = "fake"):
        super().__init__(address)
        self._up = False

    @property
    def connected(self) -> bool:
        return self._up

    async def connect(self) -> None:
        self._up = True
        log.info("fake device: no Bluetooth, the web preview is the display")

    async def disconnect(self) -> None:
        self._up = False

    async def send(self, data: bytes, expect=frozenset()) -> bool:
        await asyncio.sleep(0.03)  # roughly a real frame's round trip
        return True
