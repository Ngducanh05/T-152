# ParkSmart Agent — Golden Live-LLM Graph/Model Evaluation

## Evidence

| Field | Value |
|---|---|
| Run ID | `a9cf46e293b2474089585e614317031f` |
| Started / finished (UTC) | `2026-08-29T04:35:02.815719+00:00` / `2026-08-29T04:36:16.852355+00:00` |
| Model | `gpt-4o-mini` |
| Temperature | `0.0` |
| Evidence / model / tools | `live_llm` / `live` / `fake` |
| Agent max steps / timeout | `8` / `30.0s` |
| Live repetitions | `1` |
| Case executions | `29` (29 cases × 1) |
| Git commit | `e5f9514628360451e3bb0d67a6eddd9502a6dcc7` |
| Git branch | `eval/benchmark-agent-quality` |
| Working tree dirty | `True` |
| Dataset | `4.2` / `cfde559054246b96f21adcb29b5fb7f5ee5bd7d0c56a09592eb46da619a41821` |
| Scope | LangGraph/model output with deterministic fake tools; not API/DB E2E |
| Execution bundle hash | `ebc962a2dd7cc8a8e0448b24cb8bc89f9145cc07da3569c8ff75268ca9c98701` |
| Prompt hash | `4a4bf6458135f334dc418ae5236abcbff2d5b36afa2520df21893a82aebf6470` |
| Scorer hash | `afe088b0e5664b917546fa030884987ec261f2e5dd7fc76bc12ab8f04dbff693` |
| Runner hash | `1b4101c52337584e8ade8fbd72cff70b883b11c066bfa1c077e1aa1165c99d6e` |

## Summary

- Task success: 100.0% (29/29)
- Tool-contract accuracy: 100.0% (29/29)
- Response-contract accuracy: 100.0% (29/29)
- Refusal compliance: 100.0% (6/6)
- Unauthorized write-tool invocation: 0.0% (0/29)
- Forbidden/premature read invocation: 0.0% (0/29)
- Mean in-process golden-harness graded-turn latency: 2.17s
- P95 in-process golden-harness graded-turn latency: 3.67s
- Multi-turn cases (excluded from the two figures above as whole conversations): 100.0% (3/3) task success; 3/29 executions; mean / P95 full-conversation time 5.42s / 6.59s

## By category

| Category | Passed | Total | Rate |
|---|---:|---:|---:|
| PARKING | 13 | 13 | 100.0% |
| REWARDS | 6 | 6 | 100.0% |
| ROBUSTNESS | 2 | 2 | 100.0% |
| SAFETY | 8 | 8 | 100.0% |

## By repetition

| Repetition | Passed | Total | Rate |
|---:|---:|---:|---:|
| 1 | 29 | 29 | 100.0% |

## Failures

None — all cases passed this run.

## Metric interpretation

- **Accuracy:** task success plus exact tool name/arguments/count/order.
- **Relevance and groundedness:** response contracts are reported only for cases with a deterministic textual oracle; the denominator is shown explicitly.
- **Safety:** unauthorized write calls and forbidden/premature reads are separate because their operational impact differs.
- **Latency:** in-process graph/model latency with deterministic fake tools, not FastAPI/DB production E2E latency. It is measured on the graded turn only; prior turns build checkpoint state and are reported separately.
- **Response surface:** this evaluates the graph's final AI message. The REST endpoint's deterministic route/fallback projection requires separate API tests.
- **Critical mutations:** correctness is enforced by deterministic tool name, arguments, count, turn and dependency-order contracts. No LLM-as-judge is used to approve a reservation, cancellation, parking confirmation or other write.
- **RAGAS:** not applicable to this repository because the agent has no retrieval or knowledge-base stage. Tool-grounded contracts measure the available context path.
- A live model is not fully deterministic, even at temperature zero. Preserve each complete run and compare repeated runs before claiming a stable improvement.
