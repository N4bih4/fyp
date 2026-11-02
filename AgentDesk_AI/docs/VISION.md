# Layer 3: looking at the screen (`screen_act`)

Order of control, always: native tool -> UI Automation (`ui_inspect`/`ui_act`, layer 2) -> `screen_act` (layer 3). The executor logs `layer N` for each action.

## Pipeline
1. Focus the window and take a screenshot of that window only (PIL `ImageGrab`).
2. Windows OCR (`winsdk`, Windows.Media.Ocr, local, no cloud) finds text lines; UI Automation controls are added where there are any. `vision/boxes.py` merges them into at most 60 numbered **boxes** (UIA wins on overlap; huge containers and tiny noise dropped).
3. `vision/overlay.py` draws the boxes and numbers on a copy (max 960 px wide, JPEG).
4. The vision model (Groq `qwen/qwen3.8-27b`, else Gemini) sees the picture and the box list and answers JSON: a **box number**, an action (click, double_click, type, scroll, read, none), text, amount, answer. Coordinates it writes are never read; a box number that was not detected is refused.
5. The click goes to the centre of the **detected** box. Then the window is photographed again and compared (pixel share, word diff, line diff). "Done" is reported only when the screen changed the way the action should change it; otherwise the result says it cannot confirm.

## Safety
- The picture leaves the PC only when "cloud answers" is on; the spoken notice is "This app needs me to look at the screen, a few seconds."
- Shell windows, admin tools and password managers are never looked at. Password/secret boxes are never typed into. Boxes that send, pay, delete or install are not clicked unless the goal names them (then risk HIGH, needs a click on Approve).
- Text on the screen is data: the prompt says so, and the model can only answer with a box number from the list.
- Risk is set server-side from the goal (read = low, click/scroll/type = medium, dangerous words or a shell window = high).
- A rate-limited vision call is waited out once (up to 20 s), then reported.

## Tests
- `tests/test_u7_vision.py`: 45 tests on fake screen, OCR and model.
- `scripts/vision_live.py`: 20 steps on `scripts/vision_testapp.py`, a Tk canvas app that UI Automation cannot see into; the app writes its real state to a JSON file, which is the ground truth. Results: `docs/eval/u7_live.json`, `u7_live2.json`, `u7_live3.json`; numbered pictures in `docs/eval/u7_images/`.

## Limits
Only the front window is photographed (no multi-monitor stitching, no DPI-scaling tests beyond the primary screen); OCR depends on the Windows language pack; free-tier Groq limits make single steps take 20 s when a key is rate limited; an action with no visible effect (e.g. "Save name") is reported as unverified.
