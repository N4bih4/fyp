#!/usr/bin/env python3
"""Draws the F3 outline around a rectangle for 1.2 s and checks with a real screenshot that amber pixels appear while it is up and are gone after."""
import sys
import threading
import time

from PIL import ImageGrab

from app.tools import highlight

RECT = (300, 300, 600, 500)


def amber(p) -> bool:
    return abs(p[0] - 255) < 30 and abs(p[1] - 215) < 30 and p[2] < 40


def count(img) -> int:
    return sum(1 for x in range(296, 604, 2) for y in (297, 298, 302, 497, 498, 502) if amber(img.getpixel((x, y))))


t = threading.Thread(target=highlight.flash, args=(RECT, "check", 1.2))
t.start()
time.sleep(0.5)
during = count(ImageGrab.grab().convert("RGB"))
t.join()
time.sleep(0.3)
after = count(ImageGrab.grab().convert("RGB"))
print(f"amber pixels while drawn: {during}, after: {after}")
sys.exit(0 if during > 50 and after == 0 else 1)
