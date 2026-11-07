"""Keep the AI request small enough for the provider's per-minute token limit, in every language the user speaks.

Groq's free tier allows 8,000 tokens per minute for one request on openai/gpt-oss-120b. All 47 tool descriptions alone are ~8,100 tokens, so
sending the whole catalogue made every request fail with HTTP 413 ("Request too large ... Limit 8000, Requested 8985"). The old word list here
knew only English words, so every Urdu / Hindi / Roman Urdu command got the whole catalogue. Now the multilingual shortlist
(nlu/shortlist.py, English, Roman Urdu, Urdu, Hindi) picks the tools, and `fit_to_budget` is a hard limit on top of it.
This only narrows what the MODEL may name; the server still validates every call against the full registry and decides risk and approval.
"""
from __future__ import annotations

import json

TOOLS_BUDGET = 3500          # tokens for tool descriptions on a normal request (the rest: prompt ~500, conversation ~1000, answer ~1500)
RETRY_BUDGET = 1800          # after an HTTP 413: the smallest useful set
_CHARS_PER_TOKEN = 3.8       # measured on this catalogue: 30,913 characters = 8,134 tokens
MIN_TOOLS = 4


def estimate_tokens(obj) -> int:
    return int(len(json.dumps(obj, ensure_ascii=False)) / _CHARS_PER_TOKEN) + 1


def fit_to_budget(items: list, budget: int, name=lambda item: item["name"], keep: tuple[str, ...] = ()) -> list:
    """Drop the heaviest tool descriptions (never one in `keep`) until the rest fits `budget` tokens; at least MIN_TOOLS stay."""
    items = list(items)
    while len(items) > MIN_TOOLS and estimate_tokens(items) > budget:
        droppable = [i for i in items if name(i) not in keep]
        if not droppable:
            break
        items.remove(max(droppable, key=estimate_tokens))
    return items


def tool_metadata(registry, command, last_tools=(), budget: int = TOOLS_BUDGET):
    """Descriptions of the tools the model may use for this command: the multilingual shortlist, cut to `budget` tokens."""
    from ..nlu.shortlist import tools_for

    names = tools_for(command, registry.model_names(), (), last_tools)
    by_name = {item["name"]: item for item in registry.metadata()}
    chosen = [by_name[n] for n in names if n in by_name]
    return fit_to_budget(chosen, budget, keep=("open_application", "open_url"))
