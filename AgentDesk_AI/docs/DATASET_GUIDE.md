# Dataset guide: the local intent + slot model

The local model (xlm-roberta-base, fine-tuned, int8 ONNX, runs on the CPU in tens of milliseconds, no internet) reads one sentence and answers
**which intent** it is and **which words fill which slots**. It does not execute anything: the server still builds and validates the plan and decides the risk.

## What exists
| File | What |
|---|---|
| `data/intents.yaml` | the 61 intents, their slots, and **templates** in English, Roman Urdu, Urdu and Hindi, plus the filler values (apps, songs, folders...) |
| `ml/build_dataset.py` | expands the templates into `data/train.jsonl`, `val.jsonl`, `test.jsonl`, `test_noisy.jsonl` (+ any real sentences) |
| `ml/validate_dataset.py` | checks the files (unknown intents, slots not in the text, duplicates, language balance, train/test leaks) |
| `ml/train.py`, `ml/export_onnx.py`, `ml/evaluate.py` | train, export, measure |
| `ml/retrain.ps1` | all of the above in one go |
| `data/real/*.jsonl` | **your sentences** (this is the important part) |

## The line format (one JSON object per line)
```
{"text": "youtube pe atif aslam ka gana chala do", "intent": "youtube_play", "slots": {"query": "atif aslam ka gana"}, "lang": "roman_ur"}
{"text": "i say u can play the music on youtube not only open url", "intent": "youtube_play", "slots": {"query": null}, "lang": "en", "is_correction": true}
{"text": "file manager kholo", "intent": "open_app", "slots": {"app": "File Explorer"}, "lang": "roman_ur"}
```
* `lang`: `en` | `roman_ur` | `ur` | `hi`.
* `slots`: the slot value must be **the words as they appear in the sentence** (the model tags words). `"File Explorer"` is only valid if the sentence
  says "File Explorer"; for "file manager kholo" write `"app": "file manager"`. Turning "file manager" into File Explorer is the name matcher's job (U1).
* `is_correction`: true when the sentence corrects the previous request ("no, I meant...", "not only X").
* Put your files in `data/real/` (any name ending `.jsonl`). 80% go to training, 20% (by a hash of the text) to the test set.

## How to collect good sentences (Mirha, classmates, you)
1. **Say it, don't write it.** Use the app's microphone and copy what the transcript shows: Whisper's mistakes ("fire fox", "you tube") are exactly what the model must handle.
2. Aim for **30+ sentences per intent**, ideally 100+. Mix: about 35% English (including broken English), 35% Roman Urdu, 15% Urdu script, 15% Hindi; spelling mistakes; two languages in one sentence.
3. At least **10 different people**. Each person phrases things differently.
4. Never put passwords, real contacts' numbers or private messages in a sentence; use made-up names.
5. Run `backend\.venv\Scripts\python ml\validate_dataset.py data\real\yourfile.jsonl` until it says `0 errors`.

## Adding intents or templates
Edit `data/intents.yaml`: a template is a sentence with `{slot}` placeholders, several per line separated by ` | `; a leading `!` marks a correction.
`{app_ur}` / `{app_hi}` are fillers for the slot `app` written in Urdu / Hindi script. Then `powershell -File ml\retrain.ps1`.

## Rules the split follows (so the numbers mean something)
* The **test split is held out by template and by filler value**: the model never saw those templates or ~25% of the filler values in training. Real sentences are split by hash.
* A sentence is never in both train and test (the validator fails if it is).
* Reported numbers are for the **int8 ONNX file that the app would load**, not the PyTorch model.

## Honest limits
The seed data comes from templates written by one author. A model trained on it alone scores well on its own kind of test and **will do worse on real speakers**:
the real numbers appear only after real sentences are in `data/real/`. The Groq planner was not run on this test split (it would take hours on the free tier).

## Learning from your corrections (with consent)
`backend\.venv\Scripts\python ml\collect_corrections.py --i-consent` turns the "no, I said Firefox" corrections stored on the Memory page into `open_app` training sentences
(`data/real/corrections.jsonl`). It reads only your local database and runs only with the flag. Then `ml\retrain.ps1`.
