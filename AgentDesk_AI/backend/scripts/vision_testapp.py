#!/usr/bin/env python3
"""A small app that gives UI Automation nothing: everything is drawn on one Tk canvas (buttons, a text field, a scrolling list, a score).

Used by scripts/vision_live.py to test layer 3 (screen_act) on an app without accessibility information, with GROUND TRUTH: after every change the app
writes its real state (page, score, toggles, typed name, scroll position, clicks) to the JSON file given as the first argument, so a test can check what
really happened instead of trusting the model or the screenshot.

    python scripts/vision_testapp.py state.json
"""
from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path

W, H = 760, 460
STATE_FILE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("vision_state.json")


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("VisionTestApp")
        self.root.geometry(f"{W}x{H}+120+80")
        self.canvas = tk.Canvas(self.root, width=W, height=H, bg="#1d2433", highlightthickness=0)
        self.canvas.pack()
        self.state = {"page": "menu", "score": 0, "sound": True, "music": True, "name_text": "", "saved_name": "", "scroll": 0, "clicks": [],
                      "deleted_save": False, "focus_field": False}
        self.buttons: list[tuple[tuple[int, int, int, int], str, object]] = []
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.root.bind("<Key>", self.key)
        self.draw()

    # -- state is written after every change: the ground truth for the tests
    def save(self) -> None:
        STATE_FILE.write_text(json.dumps(self.state), encoding="utf-8")

    def button(self, x: int, y: int, w: int, h: int, label: str, action, color: str = "#2f6fed") -> None:
        self.canvas.create_rectangle(x, y, x + w, y + h, fill=color, outline="white", width=2)
        self.canvas.create_text(x + w // 2, y + h // 2, text=label, fill="white", font=("Arial", 16, "bold"))
        self.buttons.append(((x, y, x + w, y + h), label, action))

    def go(self, page: str):
        def action():
            self.state["page"] = page
        return action

    def draw(self) -> None:
        self.canvas.delete("all")
        self.buttons.clear()
        page = self.state["page"]
        self.canvas.create_text(W // 2, 34, text={"menu": "Main Menu", "game": "Game Screen", "options": "Options"}[page], fill="#ffd166", font=("Arial", 24, "bold"))
        if page == "menu":
            self.button(260, 110, 240, 60, "Start", self.go("game"))
            self.button(260, 200, 240, 60, "Options", self.go("options"))
            self.button(260, 290, 240, 60, "Credits", lambda: None, "#6c757d")
        elif page == "game":
            self.canvas.create_text(180, 100, text=f"Score: {self.state['score']}", fill="white", font=("Arial", 22))
            self.button(40, 150, 160, 54, "Add +1", lambda: self.state.__setitem__("score", self.state["score"] + 1), "#2a9d8f")
            self.button(220, 150, 160, 54, "Add +10", lambda: self.state.__setitem__("score", self.state["score"] + 10), "#2a9d8f")
            self.canvas.create_text(70, 250, text="Name:", fill="white", font=("Arial", 16))
            self.canvas.create_rectangle(120, 232, 360, 268, outline="#ffd166" if self.state["focus_field"] else "white", width=2)
            shown = self.state["name_text"] or "type here"
            self.canvas.create_text(130, 250, text=shown, fill="white" if self.state["name_text"] else "#8d99ae", anchor="w", font=("Arial", 15))
            self.button(380, 232, 150, 36, "Save name", lambda: self.state.__setitem__("saved_name", self.state["name_text"]), "#2a9d8f")
            self.canvas.create_text(560, 100, text="Scores list", fill="#ffd166", font=("Arial", 16, "bold"))
            for i in range(14):
                y = 130 + i * 24 - self.state["scroll"] * 24
                if 124 <= y <= 400:
                    self.canvas.create_text(560, y, text=f"Player {i + 1}   {1000 - i * 37}", fill="white", font=("Arial", 13))
            self.button(40, 380, 140, 46, "Back", self.go("menu"), "#6c757d")
        else:
            self.button(200, 110, 360, 56, f"Sound: {'ON' if self.state['sound'] else 'OFF'}", lambda: self.state.__setitem__("sound", not self.state["sound"]))
            self.button(200, 190, 360, 56, f"Music: {'ON' if self.state['music'] else 'OFF'}", lambda: self.state.__setitem__("music", not self.state["music"]))
            self.button(200, 270, 360, 56, "Delete save", lambda: self.state.__setitem__("deleted_save", True), "#c1121f")
            self.button(40, 380, 140, 46, "Back", self.go("menu"), "#6c757d")
        self.save()

    def click(self, event) -> None:
        self.state["clicks"] = (self.state["clicks"] + [[event.x, event.y]])[-30:]
        hit = False
        for (l, t, r, b), label, action in self.buttons:
            if l <= event.x <= r and t <= event.y <= b:
                action()
                hit = True
                break
        self.state["focus_field"] = self.state["page"] == "game" and 120 <= event.x <= 360 and 232 <= event.y <= 268
        if self.state["page"] != "game":
            self.state["focus_field"] = False
        self.draw()

    def key(self, event) -> None:
        if self.state["page"] == "game" and self.state["focus_field"]:
            if event.keysym == "BackSpace":
                self.state["name_text"] = self.state["name_text"][:-1]
            elif event.char and event.char.isprintable():
                self.state["name_text"] += event.char
            self.draw()

    def wheel(self, event) -> None:
        if self.state["page"] == "game" and event.x > 440:
            self.state["scroll"] = max(0, min(6, self.state["scroll"] + (1 if event.delta < 0 else -1)))
            self.draw()


if __name__ == "__main__":
    App().root.mainloop()
