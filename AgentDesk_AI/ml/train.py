#!/usr/bin/env python3
"""Fine-tune xlm-roberta-base for joint intent classification + slot tagging (BIO), on CPU.

    ml\\.venv\\Scripts\\python ml\\train.py [--epochs 4] [--batch 32] [--lr 4e-5] [--out ml/out]

Before training, the 250,000-word embedding table is cut down to the pieces that matter (the 16,000 most frequent sentencepiece ids, which
cover English / Urdu / Hindi well, plus every piece in the dataset). That makes the model about 100 MB after int8 export instead of ~900 MB
and cuts the optimizer memory; the mapping old id -> new id is saved next to the model (vocab_map.json) and used at run time.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ROOT, read_jsonl, slot_word_labels, words_of  # noqa: E402

BASE = "xlm-roberta-base"
KEEP_FIRST = 16000
MAX_LEN = 48


def encode_rows(tok, rows, tags, intents, id_map=None):
    """Rows -> lists of (input_ids, intent_id, slot_label_ids) using the fast `tokenizers` tokenizer (first sub-word of a word carries its tag)."""
    tag_id = {t: i for i, t in enumerate(tags)}
    out = []
    for row in rows:
        words = [w for w, _, _ in words_of(row["text"])]
        if not words:
            continue
        labels = slot_word_labels(row["text"], row.get("slots") or {})
        enc = tok.encode(words, is_pretokenized=True)
        ids, wids = enc.ids[:MAX_LEN], enc.word_ids[:MAX_LEN]
        lab, prev = [], None
        for wid in wids:
            lab.append(-100 if wid is None or wid == prev else tag_id[labels[wid]])
            prev = wid
        out.append((ids, intents.index(row["intent"]), lab))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=4e-5)
    ap.add_argument("--out", default=str(ROOT / "ml" / "out"))
    ap.add_argument("--limit", type=int, default=0, help="use only the first N training rows (a smoke test)")
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args()
    import torch
    from torch import nn
    from tokenizers import Tokenizer
    from transformers import AutoModel, get_linear_schedule_with_warmup
    from huggingface_hub import hf_hub_download

    torch.manual_seed(a.seed)
    random.seed(a.seed)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    intents, tags = labels["intents"], labels["tags"]
    tok = Tokenizer.from_file(hf_hub_download(BASE, "tokenizer.json"))
    tok.no_truncation()
    train_rows, val_rows = read_jsonl(DATA / "train.jsonl"), read_jsonl(DATA / "val.jsonl")
    if a.limit:
        random.shuffle(train_rows)
        train_rows = train_rows[:a.limit]
    train, val = encode_rows(tok, train_rows, tags, intents), encode_rows(tok, val_rows, tags, intents)
    test_ids = {i for rows in (encode_rows(tok, read_jsonl(DATA / "test.jsonl"), tags, intents),
                               encode_rows(tok, read_jsonl(DATA / "test_noisy.jsonl"), tags, intents)) for ids, _, _ in rows for i in ids}

    # vocabulary: first 16,000 ids + every id used by train / val / test sentences (their pieces must not become <unk>) + specials
    used = {i for ids, _, _ in train + val for i in ids} | test_ids | {0, 1, 2, 3}
    keep = sorted(set(range(KEEP_FIRST)) | used)
    id_map = {old: new for new, old in enumerate(keep)}
    unk_new = id_map[3]
    print(f"vocabulary kept: {len(keep)} of 250002", flush=True)

    encoder = AutoModel.from_pretrained(BASE, add_pooling_layer=False)
    old_emb = encoder.embeddings.word_embeddings.weight.data
    new_emb = nn.Embedding(len(keep), old_emb.shape[1], padding_idx=id_map[1])
    new_emb.weight.data.copy_(old_emb[torch.tensor(keep)])
    encoder.embeddings.word_embeddings = new_emb
    encoder.config.vocab_size = len(keep)
    encoder.config.pad_token_id = id_map[1]

    class JointModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = encoder
            h = encoder.config.hidden_size
            self.drop = nn.Dropout(0.1)
            self.intent_head = nn.Linear(h, len(intents))
            self.slot_head = nn.Linear(h, len(tags))

        def forward(self, input_ids, attention_mask):
            hidden = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            hidden = self.drop(hidden)
            return self.intent_head(hidden[:, 0]), self.slot_head(hidden)

    model = JointModel()
    pad_new = id_map[1]

    def batches(data, size, shuffle):
        order = list(range(len(data)))
        if shuffle:
            random.shuffle(order)
        for i in range(0, len(order), size):
            chunk = [data[j] for j in order[i:i + size]]
            width = max(len(x[0]) for x in chunk)
            ids = torch.full((len(chunk), width), pad_new, dtype=torch.long)
            mask = torch.zeros((len(chunk), width), dtype=torch.long)
            slot = torch.full((len(chunk), width), -100, dtype=torch.long)
            for r, (seq, _, lab) in enumerate(chunk):
                ids[r, :len(seq)] = torch.tensor([id_map.get(t, unk_new) for t in seq])
                mask[r, :len(seq)] = 1
                slot[r, :len(lab)] = torch.tensor(lab)
            yield ids, mask, torch.tensor([x[1] for x in chunk]), slot

    steps = a.epochs * math.ceil(len(train) / a.batch)
    heads = list(model.intent_head.parameters()) + list(model.slot_head.parameters())
    head_ids = {id(p) for p in heads}
    opt = torch.optim.AdamW([{"params": [p for p in model.parameters() if id(p) not in head_ids], "lr": a.lr},
                             {"params": heads, "lr": a.lr * 25}], weight_decay=0.01)   # the new heads learn faster than the pretrained encoder
    sched = get_linear_schedule_with_warmup(opt, int(0.08 * steps), steps)
    ce = nn.CrossEntropyLoss(ignore_index=-100)

    def evaluate(data):
        model.eval()
        right = n = slot_right = slot_n = 0
        with torch.no_grad():
            for ids, mask, y, slot in batches(data, 64, False):
                li, ls = model(ids, mask)
                right += int((li.argmax(-1) == y).sum())
                n += len(y)
                keepers = slot != -100
                slot_right += int(((ls.argmax(-1) == slot) & keepers).sum())
                slot_n += int(keepers.sum())
        model.train()
        return right / max(1, n), slot_right / max(1, slot_n)

    log = []
    best = -1.0
    started = time.time()
    model.train()
    print(f"training rows {len(train)}, val rows {len(val)}, {steps} steps", flush=True)
    for epoch in range(1, a.epochs + 1):
        t0, total, count = time.time(), 0.0, 0
        for step, (ids, mask, y, slot) in enumerate(batches(train, a.batch, True), 1):
            li, ls = model(ids, mask)
            loss = ce(li, y) + ce(ls.reshape(-1, ls.shape[-1]), slot.reshape(-1))
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            total += float(loss)
            count += 1
            if step % 25 == 0:
                print(f"  epoch {epoch} step {step} loss {total / count:.4f} ({time.time() - t0:.0f}s)", flush=True)
        acc, slot_acc = evaluate(val)
        row = {"epoch": epoch, "loss": round(total / max(1, count), 4), "val_intent_acc": round(acc, 4), "val_slot_token_acc": round(slot_acc, 4),
               "seconds": round(time.time() - t0)}
        log.append(row)
        print(json.dumps(row), flush=True)
        if acc + slot_acc > best:
            best = acc + slot_acc
            torch.save(model.state_dict(), out / "model.pt")
    (out / "vocab_map.json").write_text(json.dumps(keep), encoding="utf-8")
    (out / "train_log.json").write_text(json.dumps({"epochs": log, "train_rows": len(train), "val_rows": len(val), "seconds": round(time.time() - started),
                                                    "base": BASE, "kept_vocab": len(keep), "threads": torch.get_num_threads()}, indent=1), encoding="utf-8")
    (out / "config.json").write_text(encoder.config.to_json_string(), encoding="utf-8")
    import shutil
    shutil.copy(hf_hub_download(BASE, "tokenizer.json"), out / "tokenizer.json")
    shutil.copy(DATA / "labels.json", out / "labels.json")
    print("saved", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
