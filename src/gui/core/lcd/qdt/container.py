"""``.qdt`` container sniffing and asset extraction.

Known/observed ``.qdt`` encodings (vendor variants):

* ZIP archive (``PK\x03\x04``) holding images + layout descriptors — most common
  for lcdwiki.com downloads.
* gzip-compressed payload wrapping one of the above.
* Bare descriptor file (INI / XML / JSON text).
* Opaque binary with embedded assets — recovered by magic-byte carving
  (PNG / JPEG / BMP signatures); descriptors may be absent.

The sniffer returns an :class:`ExtractedContainer` with extracted member names,
raw descriptor texts, and carved binary assets; parsing happens in parser.py.
"""

from __future__ import annotations

import gzip
import io
import logging
import re
import struct
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath

log = logging.getLogger(__name__)

_ZIP_LOCAL_MAGIC = b"PK\x03\x04"
_GZIP_MAGIC = b"\x1f\x8b"

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_JPEG_SOI = b"\xff\xd8\xff"
_BMP_SIG = b"BM"

_DESCRIPTOR_SUFFIXES = {".json", ".xml", ".ini", ".txt", ".cfg", ".conf"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}

# Round-panel filename convention used by lcdwiki.com round themes.
_ROUND_SCREEN_RE = re.compile(r"^(\d+)\s*[xX]\s*(\d+)(?:-(\d+))?\.qdt$", re.IGNORECASE)


class ContainerKind(Enum):
    ZIP = "zip"
    GZIP = "gzip"
    DESCRIPTOR_TEXT = "descriptor_text"
    BINARY_CARVE = "binary_carve"


@dataclass
class ExtractedContainer:
    kind: ContainerKind
    members: list[str] = field(default_factory=list)
    images: dict[str, bytes] = field(default_factory=dict)          # name -> bytes
    descriptors: dict[str, str] = field(default_factory=dict)       # name -> text
    carve_log: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def screen_shape_from_filename(filename: str) -> tuple[int, int, bool] | None:
    """``480X480-3.qdt`` -> (480, 480, True). None when no convention match.

    The trailing ``-N`` index selects a sub-layout; all ``480X480-*.qdt`` files
    target the circular panel per the LCD Wiki naming scheme.
    """
    m = _ROUND_SCREEN_RE.match(filename.strip())
    if not m:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    return w, h, (w == h)


def sniff_container(data: bytes) -> ContainerKind:
    if data.startswith(_ZIP_LOCAL_MAGIC):
        return ContainerKind.ZIP
    if data[:2] == _GZIP_MAGIC:
        return ContainerKind.GZIP
    if _looks_like_text(data):
        return ContainerKind.DESCRIPTOR_TEXT
    return ContainerKind.BINARY_CARVE


def extract(data: bytes) -> ExtractedContainer:
    """Extract whatever the bytes contain; never raises for malformed input."""
    kind = sniff_container(data)
    try:
        if kind is ContainerKind.ZIP:
            out = _extract_zip(data)
        elif kind is ContainerKind.GZIP:
            inner = gzip.decompress(data)
            out = _extract_any(inner)
        elif kind is ContainerKind.DESCRIPTOR_TEXT:
            out = ExtractedContainer(kind=kind)
            out.descriptors["theme.qdt.txt"] = data.decode("utf-8", errors="replace")
        else:
            out = _carve_binary(data)
    except Exception as exc:  # malformed container: fall back to carving
        log.warning("qdt: primary extraction failed (%s); falling back to carve", exc)
        out = _carve_binary(data)
        out.warnings.append(f"primary extraction failed: {exc}")
    return out


# -- strategies ---------------------------------------------------------------


def _extract_zip(data: bytes) -> ExtractedContainer:
    out = ExtractedContainer(kind=ContainerKind.ZIP)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            name = PurePosixPath(info.filename).name or info.filename
            suffix = PurePosixPath(info.filename).suffix.lower()
            raw = zf.read(info)
            out.members.append(info.filename)
            if suffix in _IMAGE_SUFFIXES:
                out.images[name] = raw
            elif suffix in _DESCRIPTOR_SUFFIXES:
                out.descriptors[name] = raw.decode("utf-8", errors="replace")
            elif raw.startswith(_ZIP_LOCAL_MAGIC):
                # Nested archive (some vendors zip twice): recurse once.
                nested = _extract_zip(raw)
                out.images.update(nested.images)
                out.descriptors.update(nested.descriptors)
                out.warnings.append(f"recursed into nested zip: {info.filename}")
    return out


def _extract_any(data: bytes) -> ExtractedContainer:
    kind = sniff_container(data)
    if kind is ContainerKind.ZIP:
        return _extract_zip(data)
    if kind is ContainerKind.GZIP:
        return extract(data)
    if kind is ContainerKind.DESCRIPTOR_TEXT:
        out = ExtractedContainer(kind=ContainerKind.GZIP)
        out.descriptors["inner.txt"] = data.decode("utf-8", errors="replace")
        return out
    out = _carve_binary(data)
    out.kind = ContainerKind.GZIP
    return out


def _looks_like_text(data: bytes) -> bool:
    head = data[:4096].lstrip()
    if not head:
        return False
    textish = head[:512]
    printable = sum(b in (9, 10, 13) or 32 <= b < 127 or b >= 128 for b in textish)
    if printable / len(textish) < 0.95:
        return False
    decoded = head.decode("latin-1")
    probes = ("<?xml", "<layout", "[", "{", "screen", "widget", "image")
    low = decoded.lower()
    return any(p in low for p in probes)


# -- binary carving -----------------------------------------------------------


def _png_size(buf: memoryview, off: int) -> int | None:
    """Total PNG length from its IHDR chunk, or None if implausible."""
    try:
        ihdr_len = struct.unpack(">I", buf[off + 8:off + 12])[0]
        if ihdr_len != 13:
            return None
        pos = off + 8  # walk chunks until IEND
        end_limit = min(len(buf), off + 32 * 1024 * 1024)
        while pos + 8 <= end_limit:
            length = struct.unpack(">I", buf[pos:pos + 4])[0]
            ctype = bytes(buf[pos + 4:pos + 8])
            pos += 12 + length
            if ctype == b"IEND":
                return pos - off
        return None
    except struct.error:
        return None


def _jpeg_length(buf: memoryview, off: int) -> int | None:
    """Scan JPEG markers to EOI; return total length or None."""
    pos = off + 2
    end_limit = min(len(buf), off + 32 * 1024 * 1024)
    while pos + 4 <= end_limit:
        if buf[pos] != 0xFF:
            return None
        marker = buf[pos + 1]
        if marker == 0xD8:  # stray SOI
            pos += 2
            continue
        if marker == 0xD9:  # EOI
            return pos + 2 - off
        seglen = struct.unpack(">H", buf[pos + 2:pos + 4])[0]
        if seglen < 2:
            return None
        if marker == 0xDA:  # SOS: entropy-coded data follows; hunt for EOI
            eoi = buf.find(b"\xff\xd9", pos + 2, end_limit)
            return (eoi + 2 - off) if eoi != -1 else None
        pos += 2 + seglen
    return None


def _carve_binary(data: bytes) -> ExtractedContainer:
    out = ExtractedContainer(kind=ContainerKind.BINARY_CARVE)
    view = memoryview(data)

    def carve(sig: bytes, size_fn, ext: str) -> None:
        start = 0
        count = 0
        while True:
            idx = data.find(sig, start)
            if idx == -1:
                break
            start = idx + len(sig)
            size = size_fn(view, idx)
            if size and size > 64:
                name = f"carved_{count:03d}.{ext}"
                out.images[name] = bytes(data[idx:idx + size])
                out.carve_log.append(f"{name}: offset={idx} bytes={size}")
                count += 1

    carve(_PNG_SIG, _png_size, "png")
    carve(_JPEG_SOI, _jpeg_length, "jpg")
    carve(_BMP_SIG, lambda v, o: _bmp_size(v, o), "bmp")

    # Embedded ZIP central directory anywhere in the blob.
    eocd = data.rfind(b"PK\x05\x06")
    if eocd != -1:
        out.warnings.append(
            f"embedded zip central directory found at offset {eocd}; "
            "try re-extracting from that offset"
        )
    if not out.images:
        out.warnings.append("no recognizable image payloads found")
    return out


def _bmp_size(view: memoryview, off: int) -> int | None:
    try:
        # BITMAPFILEHEADER (14 B) + BITMAPINFOHEADER: derive full size from
        # pixel-array offset, DIB header size, geometry and bits-per-pixel.
        pix_off = struct.unpack("<I", view[off + 10:off + 14])[0]
        hdr = struct.unpack("<I", view[off + 14:off + 18])[0]
        w = struct.unpack("<i", view[off + 18:off + 22])[0]
        h = struct.unpack("<i", view[off + 22:off + 26])[0]
        bpp = struct.unpack("<H", view[off + 28:off + 30])[0]
        if 1 <= hdr <= 512 and 0 < w <= 4096 and 0 < abs(h) <= 4096 and bpp in (16, 24, 32):
            row = ((w * bpp + 31) // 32) * 4
            data_size = row * abs(h)
            palette = max(0, pix_off - 14 - hdr)
            return 14 + hdr + palette + data_size
    except struct.error:
        pass
    return None
