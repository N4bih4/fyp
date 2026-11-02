#!/usr/bin/env python3
"""Export the trained model (ml/out/model.pt) to ONNX and quantise it to int8 for the CPU: models/intent/intent_int8.onnx.

    ml\\.venv\\Scripts\\python ml\\export_onnx.py [--out ml/out] [--dest models/intent]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "ml" / "out"))
    ap.add_argument("--dest", default=str(ROOT / "models" / "intent"))
    a = ap.parse_args()
    import torch
    from torch import nn
    from transformers import AutoModel, XLMRobertaConfig
    from onnxruntime.quantization import QuantType, quantize_dynamic

    out, dest = Path(a.out), Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)
    labels = json.loads((out / "labels.json").read_text(encoding="utf-8"))
    config = XLMRobertaConfig.from_json_file(str(out / "config.json"))
    encoder = AutoModel.from_config(config, add_pooling_layer=False)

    class JointModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = encoder
            self.drop = nn.Dropout(0.1)
            self.intent_head = nn.Linear(config.hidden_size, len(labels["intents"]))
            self.slot_head = nn.Linear(config.hidden_size, len(labels["tags"]))

        def forward(self, input_ids, attention_mask):
            hidden = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            return self.intent_head(hidden[:, 0]), self.slot_head(hidden)

    model = JointModel()
    model.load_state_dict(torch.load(out / "model.pt", map_location="cpu"))
    model.eval()
    ids = torch.randint(4, 1000, (1, 12))
    fp32 = dest / "intent_fp32.onnx"
    torch.onnx.export(model, (ids, torch.ones_like(ids)), str(fp32), input_names=["input_ids", "attention_mask"], output_names=["intent_logits", "slot_logits"],
                      dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                                    "intent_logits": {0: "batch"}, "slot_logits": {0: "batch", 1: "seq"}}, opset_version=17, do_constant_folding=True)
    quantize_dynamic(str(fp32), str(dest / "intent_int8.onnx"), weight_type=QuantType.QInt8)
    for name in ("tokenizer.json", "labels.json", "vocab_map.json", "train_log.json"):
        shutil.copy(out / name, dest / name)
    fp32.unlink()
    for leftover in dest.glob("*.onnx.data"):
        leftover.unlink()
    size = (dest / "intent_int8.onnx").stat().st_size / 1e6
    print(f"exported {dest / 'intent_int8.onnx'} ({size:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
