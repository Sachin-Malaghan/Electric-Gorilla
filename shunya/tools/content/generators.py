"""Procedural source art: PNG textures / images and WAV sounds, generated from small typed specs.

Pure standard library (zlib, struct, wave, math) - no image or audio packages needed.
These are the studio's stand-ins for external generators; an art or audio agent describes
what it wants and gets a real source file that Unreal can import.
"""

from __future__ import annotations

import math
import random
import struct
import wave
import zlib
from pathlib import Path

Color = tuple[int, int, int]


def _clamp8(v: float) -> int:
    return max(0, min(255, int(round(v))))


def color8(rgb: list[float] | tuple[float, ...]) -> Color:
    """Accepts 0-1 floats."""
    return (_clamp8(rgb[0] * 255), _clamp8(rgb[1] * 255), _clamp8(rgb[2] * 255))


def write_png(path: Path, width: int, height: int, pixels: bytearray) -> None:
    """pixels: RGB, row-major, 3 bytes per pixel."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    stride = width * 3
    raw = b"".join(b"\x00" + bytes(pixels[y * stride : (y + 1) * stride]) for y in range(height))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


class Canvas:
    def __init__(self, width: int, height: int, background: Color):
        self.w, self.h = width, height
        self.px = bytearray(bytes(background) * (width * height))

    def set(self, x: int, y: int, c: Color) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i : i + 3] = bytes(c)

    def rect(self, x: int, y: int, w: int, h: int, c: Color) -> None:
        x0, y0, x1, y1 = max(0, x), max(0, y), min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0:
            return
        row = bytes(c) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.px[i : i + len(row)] = row

    def circle(self, cx: int, cy: int, r: int, c: Color) -> None:
        for yy in range(max(0, cy - r), min(self.h, cy + r + 1)):
            span = int(math.sqrt(max(0, r * r - (yy - cy) ** 2)))
            self.rect(cx - span, yy, 2 * span + 1, 1, c)

    def save(self, path: Path) -> None:
        write_png(path, self.w, self.h, self.px)


def generate_texture(path: Path, *, pattern: str, size: int, color_a: Color, color_b: Color, cells: int = 8, seed: int = 1) -> None:
    """pattern: grid | checker | noise | solid | gradient. Tiles seamlessly."""
    canvas = Canvas(size, size, color_a)
    cell = max(2, size // max(1, cells))
    if pattern == "grid":
        line = max(1, cell // 16)
        for k in range(0, size, cell):
            canvas.rect(k, 0, line, size, color_b)
            canvas.rect(0, k, size, line, color_b)
    elif pattern == "checker":
        for gy in range(0, size, cell):
            for gx in range(0, size, cell):
                if ((gx // cell) + (gy // cell)) % 2:
                    canvas.rect(gx, gy, cell, cell, color_b)
    elif pattern == "noise":
        rng = random.Random(seed)
        for gy in range(0, size, cell):
            for gx in range(0, size, cell):
                t = rng.random()
                canvas.rect(gx, gy, cell, cell, tuple(_clamp8(a + (b - a) * t) for a, b in zip(color_a, color_b)))  # type: ignore[arg-type]
    elif pattern == "gradient":
        for y in range(size):
            t = y / max(1, size - 1)
            canvas.rect(0, y, size, 1, tuple(_clamp8(a + (b - a) * t) for a, b in zip(color_a, color_b)))  # type: ignore[arg-type]
    elif pattern != "solid":
        raise ValueError(f"unknown pattern '{pattern}'")
    canvas.save(path)


def generate_image(path: Path, *, width: int, height: int, background: Color, shapes: list[dict]) -> None:
    """A simple board made of rectangles and circles (concept boards, layout sketches)."""
    canvas = Canvas(width, height, background)
    for s in shapes:
        c = color8(s["color"])
        if s["shape"] == "rect":
            canvas.rect(int(s["x"]), int(s["y"]), int(s["w"]), int(s["h"]), c)
        elif s["shape"] == "circle":
            canvas.circle(int(s["x"]), int(s["y"]), int(s["r"]), c)
        else:
            raise ValueError(f"unknown shape '{s['shape']}'")
    canvas.save(path)


SAMPLE_RATE = 44100


def _wave_value(kind: str, phase: float, rng: random.Random) -> float:
    if kind == "sine":
        return math.sin(2 * math.pi * phase)
    if kind == "square":
        return 1.0 if (phase % 1.0) < 0.5 else -1.0
    if kind == "triangle":
        return 4 * abs((phase % 1.0) - 0.5) - 1
    if kind == "saw":
        return 2 * (phase % 1.0) - 1
    if kind == "noise":
        return rng.uniform(-1, 1)
    raise ValueError(f"unknown waveform '{kind}'")


def generate_sound(path: Path, *, notes: list[dict], seed: int = 1) -> float:
    """notes: [{frequency, duration, waveform, volume, decay, slide_to}] played one after another.

    `decay` 0..1 is how much the note fades by its end; `slide_to` glides the pitch.
    Each note gets a short attack/release so there are no clicks. Returns the duration in seconds.
    """
    rng = random.Random(seed)
    samples: list[int] = []
    for note in notes:
        n = max(1, int(float(note["duration"]) * SAMPLE_RATE))
        f0 = float(note.get("frequency", 440.0))
        f1 = float(note.get("slide_to") or f0)
        volume = max(0.0, min(1.0, float(note.get("volume", 0.6))))
        decay = max(0.0, min(1.0, float(note.get("decay", 0.5))))
        kind = note.get("waveform", "sine")
        edge = min(n // 2, int(0.006 * SAMPLE_RATE))
        phase = 0.0
        for i in range(n):
            t = i / n
            phase += (f0 + (f1 - f0) * t) / SAMPLE_RATE
            env = (1.0 - decay * t) * min(1.0, i / max(1, edge), (n - 1 - i) / max(1, edge))
            value = 0.0 if f0 <= 0 else _wave_value(kind, phase, rng)
            samples.append(int(max(-1.0, min(1.0, value * volume * env)) * 32767))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return len(samples) / SAMPLE_RATE
