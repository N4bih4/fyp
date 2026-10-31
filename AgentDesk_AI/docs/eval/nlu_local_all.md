# NLU evaluation — mode `local`, split `all`

Date: 2026-10-31 (UTC). Dataset: `backend/tests/nlu_eval/commands.jsonl` (300 items). Platform: Linux / Python 3.13.18. Run time: 0.1 s.

Gate G3 thresholds: intent+tool >= 90%, exact args >= 85%, 0 invented tools, 0 approval bypasses.

**Gate G3: PASS** — intent_tool pass, exact_args pass, invented_tools pass, approval_bypasses pass

| slice | n | intent+tool | exact args | invented | bypasses | lang detect | deferred |
|---|---|---|---|---|---|---|---|
| overall | 300 | 99.3% | 99.3% | 0 | 0 | 98.7% | 2 |
| en | 92 | 98.9% | 98.9% | 0 | 0 | 98.9% | 1 |
| roman_ur | 88 | 98.9% | 98.9% | 0 | 0 | 96.6% | 1 |
| ur | 60 | 100.0% | 100.0% | 0 | 0 | 100.0% | 0 |
| hi | 60 | 100.0% | 100.0% | 0 | 0 | 100.0% | 0 |
| dev | 201 | 99.0% | 99.0% | 0 | 0 | 98.0% | 2 |
| holdout | 99 | 100.0% | 100.0% | 0 | 0 | 100.0% | 0 |

In `local` mode an item the matcher is not confident about (< 0.85) is counted as wrong, so these numbers are a lower bound for the Groq pipeline.

## Independent paraphrase probe

`tests/nlu_eval/paraphrases.jsonl`: 40 new phrasings written after the matcher and never used for tuning (intent + tools only).

- correct: 20
- deferred (sent to the LLM in the pipeline): 20
- **confidently wrong: 0**


## Items not exactly right (2)

| id | command | expected | predicted | note |
|---|---|---|---|---|
| en-067 | write an email to sara@example.com about the project delay | email_draft ['compose_email'] | None None | deferred |
| roman_ur-071 | sara@example.com ko project delay ke bare mein email likho | email_draft ['compose_email'] | None None | deferred |
