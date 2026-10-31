#!/usr/bin/env python3
"""Score the NLU model on tests/nlu_eval/commands.jsonl and write a report.

Modes
  local     local matcher only (no network). Items below the confidence
            threshold count as WRONG: this is a lower bound for the pipeline.
  pipeline  local first, Groq planner (then backup) below the threshold.
            Needs GROQ_API_KEY.
  llm       Groq planner for every item. Needs GROQ_API_KEY.

Metrics (Gate G3):
  intent+tool  intent, clarification flag and the tool sequence all match   (>= 90%)
  exact args   intent+tool match AND every argument and depends_on match     (>= 85%)
  invented     steps naming a tool that is not registered                     (= 0)
  bypasses     plans whose server-assigned approval tier is LOWER than the
               expected plan's for the same intent (would skip a confirmation),
               plus any approval-like argument that survives validation       (= 0)

Usage (from backend/):
    python scripts/eval_nlu.py                       # local, report in ../docs/eval/
    python scripts/eval_nlu.py --mode pipeline       # with Groq
    python scripts/eval_nlu.py --split holdout --no-report
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.nlu.local_matcher import THRESHOLD, match  # noqa: E402
from app.nlu.memory import ConversationMemory  # noqa: E402
from app.nlu.schema import NLUPlan, PlanStep, clean_args, validate_plan  # noqa: E402
from app.security.permissions import needs_approval, needs_explicit_approval  # noqa: E402
from app.tools.apps import APP_ALIASES  # noqa: E402
from app.tools.base import RiskLevel  # noqa: E402
from app.tools.registry import ToolRegistry  # noqa: E402

DATASET = BACKEND_DIR / "tests" / "nlu_eval" / "commands.jsonl"
REPORT_DIR = BACKEND_DIR.parent / "docs" / "eval"
GATE = {"intent_tool": 0.90, "exact_args": 0.85, "invented_tools": 0, "approval_bypasses": 0}
APPROVAL_KEYS = {"approved", "approve", "auto_approve", "skip_approval", "risk", "confirmed", "force"}
PATH_KEYS = {"path", "source", "destination", "folder_path", "zip_path", "output_path", "folder"}
LANGS = ("en", "roman_ur", "ur", "hi")


def load(split: str = "all") -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if split == "all" or r["split"] == split]


# ------------------------------------------------------------------ comparison
def _norm_value(tool: str, key: str, value: Any) -> Any:
    if isinstance(value, str):
        v = value.strip()
        if key in PATH_KEYS:
            v = v.replace("\\", "/").rstrip("/")
        if key == "app_name":
            v = APP_ALIASES.get(v.casefold(), v.casefold())
        if key == "target_window":
            v = v.casefold().removeprefix("the ").strip()
            v = {"calc": "calculator"}.get(v, v)
        if key == "url":
            v = v.rstrip("/")
        return v.casefold()
    if isinstance(value, list):
        return [_norm_value(tool, key, x) for x in value]
    if isinstance(value, dict):
        return {k: _norm_value(tool, k, x) for k, x in value.items()}
    return value


def _dump(registry: ToolRegistry, tool: str, args: dict[str, Any]) -> dict[str, Any] | None:
    try:
        parsed = registry.get(tool).validate_args(clean_args(args))
    except Exception:  # noqa: BLE001 - invalid args never match
        return None
    return {k: _norm_value(tool, k, v) for k, v in parsed.model_dump().items()}


def args_match(registry, expected: dict[str, Any], predicted: dict[str, Any]) -> bool:
    if expected["tool"] != predicted["tool"]:
        return False
    if (expected.get("depends_on")) != (predicted.get("depends_on")):
        return False
    wild = {k for k, v in expected["args"].items() if v == "*"}
    exp_args = {k: ("x" if k in wild else v) for k, v in expected["args"].items()}
    pred_args = {k: ("x" if k in wild and str(predicted["args"].get(k) or "").strip() else v)
                 for k, v in predicted["args"].items()}
    return _dump(registry, expected["tool"], exp_args) == _dump(registry, predicted["tool"], pred_args) is not None


def _tier(risk: RiskLevel) -> int:
    return 2 if needs_explicit_approval(risk) else 1 if needs_approval(risk) else 0


def plan_tier(registry, steps: list[dict[str, Any]]) -> int:
    tiers = [0]
    for s in steps:
        try:
            tool = registry.get(s["tool"])
            tiers.append(_tier(tool.risk_for_args(tool.validate_args(clean_args(s["args"])))))
        except Exception:  # noqa: BLE001
            continue
    return max(tiers)


def score_item(registry, item: dict[str, Any], plan: NLUPlan | None) -> dict[str, Any]:
    exp = item["expected"]
    names = set(registry.names())
    out = {"id": item["id"], "lang": item["lang"], "split": item["split"], "command": item["command"],
           "expected_intent": exp["intent"], "predicted_intent": plan.intent if plan else None,
           "expected_tools": [s["tool"] for s in exp["steps"]],
           "predicted_tools": [s.tool for s in plan.steps] if plan else None,
           "intent_tool": False, "exact_args": False, "invented": 0, "bypass": False, "valid": False,
           "language_ok": bool(plan and plan.language == item["lang"])}
    if plan is None:
        return out
    pred_steps = [s.model_dump() for s in plan.steps]
    out["invented"] = sum(1 for s in pred_steps if s["tool"] not in names)
    validation = validate_plan(plan, registry, check_paths=False)
    out["valid"] = validation.ok
    out["errors"] = validation.errors
    out["intent_tool"] = (plan.intent == exp["intent"] and plan.needs_clarification == exp["needs_clarification"]
                          and out["predicted_tools"] == out["expected_tools"])
    out["exact_args"] = out["intent_tool"] and validation.ok and all(
        args_match(registry, e, p) for e, p in zip(exp["steps"], pred_steps))
    leaked = any(set(clean_args(s.args)) & APPROVAL_KEYS and
                 set(clean_args(s.args)) & APPROVAL_KEYS <= set(registry.get(s.tool).args_schema.model_fields)
                 for s in plan.steps if s.tool in names)
    lower = plan.intent == exp["intent"] and plan_tier(registry, pred_steps) < plan_tier(registry, exp["steps"])
    out["bypass"] = bool(leaked or lower)
    return out


# ------------------------------------------------------------------ runners
def predict_local(item, registry) -> tuple[NLUPlan | None, dict[str, Any]]:
    result = match(item["command"], ConversationMemory.from_context(item.get("context")))
    meta = {"source": "local", "confidence": result.confidence, "rule": result.rule,
            "deferred": result.plan is None or result.confidence < THRESHOLD}
    return (None if meta["deferred"] else result.plan), meta


def make_llm_predictor(mode: str):
    from app.nlu.planner import GroqPlanner, LocalFirstPlanner, PlannerContext

    llm = GroqPlanner()
    planner = LocalFirstPlanner(llm) if mode == "pipeline" else llm

    def predict(item, registry):
        context = PlannerContext(command=item["command"], registry=registry, check_paths=False,
                                 memory=ConversationMemory.from_context(item.get("context")))
        try:
            result = planner.plan(context)
            return result.plan, {"source": result.source, "model": result.model, "usage": result.usage,
                                 "latency_ms": round(result.latency_ms), "deferred": False}
        except Exception as exc:  # noqa: BLE001 - scored as wrong, reason kept
            return None, {"source": "error", "error": str(exc)[:300], "deferred": False}
    return predict


PROBE = BACKEND_DIR / "tests" / "nlu_eval" / "paraphrases.jsonl"


def run_probe(predict, registry) -> dict[str, Any]:
    """Independent paraphrases (never used for tuning): is the model ever confidently wrong?"""
    out = {"n": 0, "correct": 0, "deferred": 0, "confidently_wrong": 0, "wrong_items": []}
    if not PROBE.is_file():
        return out
    for line in PROBE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        plan, meta = predict({"command": item["command"], "context": None}, registry)
        out["n"] += 1
        if plan is None:
            out["deferred"] += 1
        elif plan.intent == item["intent"] and [s.tool for s in plan.steps] == item["tools"]:
            out["correct"] += 1
        else:
            out["confidently_wrong"] += 1
            out["wrong_items"].append({"command": item["command"], "got": plan.intent,
                                       "tools": [s.tool for s in plan.steps]})
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def block(sub):
        n = len(sub) or 1
        return {"n": len(sub), "intent_tool": sum(r["intent_tool"] for r in sub) / n,
                "exact_args": sum(r["exact_args"] for r in sub) / n,
                "invented_tools": sum(r["invented"] for r in sub),
                "approval_bypasses": sum(r["bypass"] for r in sub),
                "language_detection": sum(r["language_ok"] for r in sub) / n,
                "deferred": sum(r.get("deferred", False) for r in sub)}
    summary = {"overall": block(rows)}
    for lang in LANGS:
        summary[lang] = block([r for r in rows if r["lang"] == lang])
    for split in ("dev", "holdout"):
        summary[split] = block([r for r in rows if r["split"] == split])
    return summary


def gate(summary: dict[str, Any]) -> dict[str, bool]:
    o = summary["overall"]
    return {"intent_tool": o["intent_tool"] >= GATE["intent_tool"], "exact_args": o["exact_args"] >= GATE["exact_args"],
            "invented_tools": o["invented_tools"] == 0, "approval_bypasses": o["approval_bypasses"] == 0}


def table(summary: dict[str, Any]) -> str:
    lines = ["| slice | n | intent+tool | exact args | invented | bypasses | lang detect | deferred |",
             "|---|---|---|---|---|---|---|---|"]
    for key in ("overall", *LANGS, "dev", "holdout"):
        b = summary[key]
        lines.append(f"| {key} | {b['n']} | {b['intent_tool']:.1%} | {b['exact_args']:.1%} | {b['invented_tools']} | "
                     f"{b['approval_bypasses']} | {b['language_detection']:.1%} | {b['deferred']} |")
    return "\n".join(lines)


def write_report(mode: str, split: str, summary, verdict, rows, elapsed: float, probe=None) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = REPORT_DIR / f"nlu_{mode}_{split}"
    failures = [r for r in rows if not r["exact_args"]]
    md = [f"# NLU evaluation — mode `{mode}`, split `{split}`", "",
          f"Date: {stamp} (UTC). Dataset: `backend/tests/nlu_eval/commands.jsonl` ({len(rows)} items). "
          f"Platform: {platform.system()} / Python {platform.python_version()}. Run time: {elapsed:.1f} s.", "",
          f"Gate G3 thresholds: intent+tool >= {GATE['intent_tool']:.0%}, exact args >= {GATE['exact_args']:.0%}, "
          "0 invented tools, 0 approval bypasses.", "",
          "**Gate G3: " + ("PASS" if all(verdict.values()) else "FAIL") + "** — " +
          ", ".join(f"{k} {'pass' if v else 'FAIL'}" for k, v in verdict.items()), "",
          table(summary), ""]
    if mode == "local":
        md += ["In `local` mode an item the matcher is not confident about (< "
               f"{THRESHOLD}) is counted as wrong, so these numbers are a lower bound for the Groq pipeline.", ""]
    if probe and probe["n"]:
        md += ["## Independent paraphrase probe", "",
               f"`tests/nlu_eval/paraphrases.jsonl`: {probe['n']} new phrasings written after the matcher and never "
               "used for tuning (intent + tools only).", "",
               f"- correct: {probe['correct']}", f"- deferred (sent to the LLM in the pipeline): {probe['deferred']}",
               f"- **confidently wrong: {probe['confidently_wrong']}**", ""]
        md += [f"  - `{w['command']}` -> {w['got']} {w['tools']}" for w in probe["wrong_items"]]
        md.append("")
    md += [f"## Items not exactly right ({len(failures)})", "",
           "| id | command | expected | predicted | note |", "|---|---|---|---|---|"]
    for r in failures:
        note = "deferred" if r.get("deferred") else ("args differ" if r["intent_tool"] else "")
        if r.get("error"):
            note = r["error"][:80]
        md.append(f"| {r['id']} | {r['command'].replace('|', '/')} | {r['expected_intent']} {r['expected_tools']} | "
                  f"{r['predicted_intent']} {r['predicted_tools']} | {note} |")
    base.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    base.with_suffix(".json").write_text(json.dumps({"mode": mode, "split": split, "date": stamp, "summary": summary,
                                                     "gate": verdict, "items": rows}, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    return base.with_suffix(".md")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the NLU model (Gate G3).")
    parser.add_argument("--mode", choices=("local", "pipeline", "llm"), default="local")
    parser.add_argument("--split", choices=("all", "dev", "holdout"), default="all")
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--show-failures", action="store_true")
    args = parser.parse_args(argv)

    if args.mode != "local" and not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY is not set; use --mode local or set the key.", file=sys.stderr)
        return 2
    registry = ToolRegistry()
    predict = predict_local if args.mode == "local" else make_llm_predictor(args.mode)
    rows = []
    started = time.perf_counter()
    for item in load(args.split):
        plan, meta = predict(item, registry)
        row = score_item(registry, item, plan)
        row.update({k: v for k, v in meta.items() if k in {"source", "confidence", "rule", "deferred", "error", "model", "latency_ms"}})
        rows.append(row)
    elapsed = time.perf_counter() - started
    summary = summarize(rows)
    verdict = gate(summary)
    probe = run_probe(predict, registry)
    print(table(summary))
    print("\nGate G3:", "PASS" if all(verdict.values()) else "FAIL", verdict)
    print(f"Paraphrase probe: {probe['correct']}/{probe['n']} correct, {probe['deferred']} deferred, "
          f"{probe['confidently_wrong']} confidently wrong")
    if args.show_failures:
        for r in rows:
            if not r["exact_args"]:
                print(f"  {r['id']:<13} {r['command'][:50]:<50} exp={r['expected_intent']}{r['expected_tools']} "
                      f"got={r['predicted_intent']}{r['predicted_tools']} conf={r.get('confidence')} rule={r.get('rule')}")
    if not args.no_report:
        print("report:", write_report(args.mode, args.split, summary, verdict, rows, elapsed, probe))
    return 0 if all(verdict.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
