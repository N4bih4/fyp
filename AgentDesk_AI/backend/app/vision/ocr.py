"""Windows' own OCR (Windows.Media.Ocr, offline, no model download): lines of text with their rectangles.

`OcrEngine` is the interface the tool uses; tests give a fake one. The real one needs Windows 10+ and the `winsdk` package, and recognises the
languages installed for the user (check Settings > Time & language > Language; en-US is normally there).
"""
from __future__ import annotations

import asyncio
import io
from typing import Protocol

from .boxes import OcrLine


class OcrEngine(Protocol):
    def recognize(self, image) -> list[OcrLine]: ...


class OcrUnavailable(RuntimeError):
    """OCR cannot run here (not Windows, winsdk missing, no language pack)."""


def split_by_gaps(words: list[tuple[str, tuple[int, int, int, int]]], factor: float = 1.6) -> list[OcrLine]:
    """One OCR "line" can span two buttons that sit on the same row ("Play     Stop"): cut it where the space between words is
    much wider than the text is tall, so each label is its own box."""
    if not words:
        return []
    height = max(1, sum(w[1][3] - w[1][1] for w in words) // len(words))
    groups: list[list[tuple[str, tuple[int, int, int, int]]]] = [[words[0]]]
    for word in words[1:]:
        gap = word[1][0] - groups[-1][-1][1][2]
        if gap > factor * height:
            groups.append([word])
        else:
            groups[-1].append(word)
    out = []
    for g in groups:
        rect = (min(w[1][0] for w in g), min(w[1][1] for w in g), max(w[1][2] for w in g), max(w[1][3] for w in g))
        out.append(OcrLine(" ".join(w[0] for w in g), rect, g))
    return out


class WindowsOcr:
    def __init__(self) -> None:
        try:
            from winsdk.windows.media.ocr import OcrEngine as _Engine
        except ImportError as exc:
            raise OcrUnavailable("Windows OCR needs the winsdk package on Windows.") from exc
        self._Engine = _Engine
        if _Engine.try_create_from_user_profile_languages() is None:
            raise OcrUnavailable("No OCR language is installed for this user.")

    def recognize(self, image) -> list[OcrLine]:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._recognize(image))
        finally:
            loop.close()

    async def _recognize(self, image) -> list[OcrLine]:
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
        buf = io.BytesIO()
        image.convert("RGB").save(buf, "PNG")
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(buf.getvalue())
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        engine = self._Engine.try_create_from_user_profile_languages()
        result = await engine.recognize_async(bitmap)
        lines: list[OcrLine] = []
        for line in result.lines:
            words = [(w.text, (round(w.bounding_rect.x), round(w.bounding_rect.y), round(w.bounding_rect.x + w.bounding_rect.width),
                               round(w.bounding_rect.y + w.bounding_rect.height))) for w in line.words]
            lines.extend(split_by_gaps(words))
        return lines


_engine: OcrEngine | None = None


def get_ocr() -> OcrEngine:
    global _engine
    if _engine is None:
        _engine = WindowsOcr()
    return _engine


def set_ocr(engine: OcrEngine | None) -> None:
    global _engine
    _engine = engine
