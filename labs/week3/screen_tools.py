"""Screenshot the "Browser agent" window with mss.

desktop.py keeps that window title so this file can find it. The grab is the
whole window (browser on the left, chat on the right). If the window cannot be
found, the grab is the primary monitor and the region is "full".
"""

from __future__ import annotations

import ctypes
import io
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

WINDOW_TITLE = "Browser agent"  # must match desktop.WINDOW_TITLE
MAX_SIDE = 1568
SHOT_DIR = Path(__file__).resolve().parent / "output" / "screenshots"

_ON_SCREEN = 1
_SKIP_DESKTOP = 16
_UTF8 = 0x08000100
_FLOAT64 = 6
_INT64 = 4


@dataclass
class Screenshot:
    png: bytes
    width: int
    height: int
    captured_at: str
    region: str
    path: Path | None = None

    def summary(self) -> dict[str, str]:
        return {
            "captured_at": self.captured_at,
            "region": self.region,
            "size": f"{self.width}x{self.height}",
            "note": (
                "This image is the Browser agent window: the webpage or PDF is on the left, "
                "the chat is on the right. Describe the left side."
                if self.region == "window"
                else "The Browser agent window was not found, so this is the full primary monitor."
            ),
        }


def _cf():
    cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFNumberGetValue.restype = ctypes.c_bool
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    cf.CFGetTypeID.restype = ctypes.c_ulong
    cf.CFGetTypeID.argtypes = [ctypes.c_void_p]
    cf.CFStringGetTypeID.restype = ctypes.c_ulong
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    return cf, cg


def _cstr(cf, text: str) -> ctypes.c_void_p:
    return cf.CFStringCreateWithCString(None, text.encode(), _UTF8)


def _read_string(cf, value: ctypes.c_void_p) -> str:
    if not value or cf.CFGetTypeID(value) != cf.CFStringGetTypeID():
        return ""
    buf = ctypes.create_string_buffer(512)
    cf.CFStringGetCString(value, buf, len(buf), _UTF8)
    return buf.value.decode(errors="replace")


def _read_number(cf, value: ctypes.c_void_p) -> float | None:
    if not value:
        return None
    out = ctypes.c_double()
    if cf.CFNumberGetValue(value, _FLOAT64, ctypes.byref(out)):
        return out.value
    whole = ctypes.c_int64()
    if cf.CFNumberGetValue(value, _INT64, ctypes.byref(whole)):
        return float(whole.value)
    return None


def _window_rect(title: str) -> dict[str, int] | None:
    """Bounds of the on-screen window with this title, in screen points."""
    cf, cg = _cf()
    keys = {name: _cstr(cf, name) for name in ("kCGWindowName", "kCGWindowOwnerPID", "kCGWindowBounds")}
    bounds_keys = {name: _cstr(cf, name) for name in ("X", "Y", "Width", "Height")}
    windows = cg.CGWindowListCopyWindowInfo(_ON_SCREEN | _SKIP_DESKTOP, 0)
    found: dict[str, int] | None = None
    own_largest: dict[str, int] | None = None
    try:
        count = cf.CFArrayGetCount(windows) if windows else 0
        for index in range(count):
            info = cf.CFArrayGetValueAtIndex(windows, index)
            name = _read_string(cf, cf.CFDictionaryGetValue(info, keys["kCGWindowName"]))
            bounds = cf.CFDictionaryGetValue(info, keys["kCGWindowBounds"])
            if not bounds:
                continue
            rect = {
                axis: int(_read_number(cf, cf.CFDictionaryGetValue(bounds, bounds_keys[axis])) or 0)
                for axis in ("X", "Y", "Width", "Height")
            }
            if rect["Width"] < 200 or rect["Height"] < 200:
                continue
            area = rect["Width"] * rect["Height"]
            owner = _read_number(cf, cf.CFDictionaryGetValue(info, keys["kCGWindowOwnerPID"]))
            if name == title and (found is None or area > found["Width"] * found["Height"]):
                found = rect
            elif owner == os.getpid() and (own_largest is None or area > own_largest["Width"] * own_largest["Height"]):
                own_largest = rect
    finally:
        if windows:
            cf.CFRelease(windows)
        for ref in (*keys.values(), *bounds_keys.values()):
            cf.CFRelease(ref)
    chosen = found or own_largest
    if not chosen:
        return None
    return {"left": chosen["X"], "top": chosen["Y"], "width": chosen["Width"], "height": chosen["Height"]}


def _grab(region: dict[str, int] | None) -> tuple[bytes, str]:
    import mss
    import mss.tools

    with mss.MSS() as sct:
        area = region or sct.monitors[1]
        raw = sct.grab(area)
        png = mss.tools.to_png(raw.rgb, raw.size)
    return png, ("window" if region else "full")


def _shrink(png: bytes) -> tuple[bytes, int, int]:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    samples = [img.getpixel((x, y)) for x in range(0, img.width, max(1, img.width // 12)) for y in range(0, img.height, max(1, img.height // 12))]
    if samples and all(max(px) < 8 for px in samples):
        raise RuntimeError(
            "The screenshot is black. Grant Screen Recording permission to the app that "
            "launched this window (Terminal or Cursor), then try again."
        )
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue(), img.width, img.height


def capture_screen() -> Screenshot:
    """Screenshot the Browser agent window, or the primary monitor if it is not open."""
    rect = _window_rect(WINDOW_TITLE)
    png, region = _grab(rect)
    png, width, height = _shrink(png)
    now = datetime.now().astimezone()
    shot = Screenshot(
        png=png,
        width=width,
        height=height,
        captured_at=now.isoformat(timespec="seconds"),
        region=region,
    )
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    shot.path = SHOT_DIR / f"shot_{now:%Y%m%d_%H%M%S}.png"
    shot.path.write_bytes(png)
    return shot
