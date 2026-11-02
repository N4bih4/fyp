"""Candidate boxes: the only things the vision model may point at.

A box is a rectangle the PROGRAM detected, either a UI Automation control (even a poorly described one) or a line of text found by OCR.
The picture sent to the model has these boxes drawn on it with their numbers; the model answers with a number. The program turns a number back into
the centre of THAT rectangle. A coordinate written by the model is never used, so a model cannot make the program click somewhere it did not detect.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MAX_BOXES = 60
MIN_SIDE = 7          # pixels; smaller than this is noise
MAX_TEXT = 80


@dataclass
class Box:
    id: int
    rect: tuple[int, int, int, int]       # left, top, right, bottom, in the coordinates of the captured image
    text: str = ""
    source: str = "ocr"                    # ocr | uia
    kind: str = ""                         # a UIA control type, "" for OCR text
    enabled: bool = True
    password: bool = False

    @property
    def center(self) -> tuple[int, int]:
        l, t, r, b = self.rect
        return (l + r) // 2, (t + b) // 2

    @property
    def area(self) -> int:
        return max(0, self.rect[2] - self.rect[0]) * max(0, self.rect[3] - self.rect[1])

    def describe(self) -> str:
        label = f'"{self.text[:MAX_TEXT]}"' if self.text else "(no text)"
        return f"{self.id}: {label}" + (f" [{self.kind}]" if self.kind else "")


@dataclass
class OcrLine:
    text: str
    rect: tuple[int, int, int, int]
    words: list[tuple[str, tuple[int, int, int, int]]] = field(default_factory=list)


def _inter(a, b) -> int:
    l, t, r, bt = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return max(0, r - l) * max(0, bt - t)


def _area(a) -> int:
    return max(0, a[2] - a[0]) * max(0, a[3] - a[1])


def build_boxes(size: tuple[int, int], ocr_lines: list[OcrLine], uia: list[dict] | None = None, limit: int = MAX_BOXES) -> list[Box]:
    """Merge UIA controls and OCR lines into one numbered list (reading order). UIA wins where both describe the same place.

    `uia` items: {"rect": (l, t, r, b) in image coordinates, "name", "type", "enabled", "password"}.
    """
    width, height = size
    candidates: list[Box] = []
    for c in uia or []:
        l, t, r, b = (max(0, c["rect"][0]), max(0, c["rect"][1]), min(width, c["rect"][2]), min(height, c["rect"][3]))
        if r - l < MIN_SIDE or b - t < MIN_SIDE or (r - l) * (b - t) > 0.6 * width * height:
            continue          # off the picture, noise, or the whole window itself
        candidates.append(Box(0, (l, t, r, b), (c.get("name") or "").strip(), "uia", c.get("type", ""), bool(c.get("enabled", True)), bool(c.get("password"))))
    for line in ocr_lines:
        l, t, r, b = line.rect
        if r - l < MIN_SIDE or b - t < MIN_SIDE or not line.text.strip():
            continue
        covering = [u for u in candidates if u.source == "uia" and _inter(u.rect, line.rect) >= 0.6 * _area(line.rect)]
        if covering:
            best = min(covering, key=lambda u: u.area)
            if not best.text:
                best.text = line.text.strip()       # the control had no name: the picture tells what it says
            continue
        candidates.append(Box(0, (l, t, r, b), line.text.strip(), "ocr"))
    # remove near-duplicates (the same text found twice, or a box inside a bigger box with the same words)
    unique: list[Box] = []
    for box in sorted(candidates, key=lambda x: (x.source != "uia", -x.area)):
        if any(_inter(box.rect, u.rect) >= 0.8 * min(box.area, u.area) and (not box.text or box.text.casefold() in u.text.casefold() or u.text.casefold() in box.text.casefold()) for u in unique):
            continue
        unique.append(box)
    unique.sort(key=lambda x: (x.rect[1] // 14, x.rect[0]))
    unique = unique[:limit]
    for i, box in enumerate(unique, 1):
        box.id = i
    return unique
