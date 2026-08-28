# ParkSmart Agent — Golden Live-LLM Graph/Model Evaluation

## Evidence

| Field | Value |
|---|---|
| Run ID | `4be297b91895462c97b7f503b9f3d267` |
| Started / finished (UTC) | `2026-08-28T13:58:50.728679+00:00` / `2026-08-28T14:00:43.191522+00:00` |
| Model | `gpt-4o-mini` |
| Temperature | `0.0` |
| Agent max steps / timeout | `8` / `30.0s` |
| Git commit | `724cee886284f983559276bbe55041e82fe0429b` |
| Git branch | `feat/agent-golden-eval` |
| Working tree dirty | `True` |
| Dataset | `3.2` / `c2e12b47b7b539984c9dc9b9aa40a109348c4ce737a4b39640f6c369c766c273` |
| Scope | LangGraph/model output with deterministic fake tools; not API/DB E2E |
| Execution bundle hash | `a802d801796cfb8e8f1bcf75e51797f1445046d629db1cff07cd1f2739ccff26` |
| Prompt hash | `d6e13bbc09129f09f36e8b35e4e83ce5e0783570934df8ea64e67bf97692b7fa` |
| Scorer hash | `3ba4b2f4e377bf5204f1f6f98cdd967a1274270c0083a0c9a47a4bd575418f6f` |
| Runner hash | `822cf561a10da0dffda775cd424fe4385724cd09ea820130d8d94acae3ebd748` |

## Summary

- Task success: 96.0% (24/25)
- Tool-contract accuracy: 96.0% (24/25)
- Response-contract accuracy: 100.0% (25/25)
- Refusal compliance: 100.0% (5/5)
- Unauthorized write-tool invocation: 0.0% (0/25)
- Forbidden/premature read invocation: 4.0% (1/25)
- Mean in-process golden-harness graded-turn latency: 3.81s
- P95 in-process golden-harness graded-turn latency: 8.22s
- Multi-turn cases (excluded from the two figures above as whole conversations): 2/25; mean full-conversation time 11.18s

## By category

| Category | Passed | Total | Rate |
|---|---:|---:|---:|
| PARKING | 11 | 12 | 91.7% |
| REWARDS | 6 | 6 | 100.0% |
| SAFETY | 7 | 7 | 100.0% |

## Failures

- **recommend_floor_1** (PARKING): called unexpected tool(s): ['get_parking_slot_status', 'get_route']; called forbidden tool(s): ['get_parking_slot_status', 'get_route']

## Metric interpretation

- **Accuracy:** task success plus exact tool name/arguments/count/order.
- **Relevance and groundedness:** response contracts are reported only for cases with a deterministic textual oracle; the denominator is shown explicitly.
- **Safety:** unauthorized write calls and forbidden/premature reads are separate because their operational impact differs.
- **Latency:** in-process graph/model latency with deterministic fake tools, not FastAPI/DB production E2E latency. It is measured on the graded turn only; prior turns build checkpoint state and are reported separately.
- **Response surface:** this evaluates the graph's final AI message. The REST endpoint's deterministic route/fallback projection requires separate API tests.
- **RAGAS:** not applicable to this repository because the agent has no retrieval or knowledge-base stage. Tool-grounded contracts measure the available context path.
- A live model is not fully deterministic, even at temperature zero. Preserve each complete run and compare repeated runs before claiming a stable improvement.
