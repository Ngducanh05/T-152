"""Validate a complete golden artifact and render its metrics report."""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from eval.artifacts import (  # noqa: E402
    ARTIFACT_SCHEMA_VERSION,
    dataset_sha256,
    validate_result_record,
)
from eval.golden_cases import GOLDEN_CASES, GOLDEN_DATASET_VERSION  # noqa: E402
from src.services.llm import EFFECTIVE_LLM_TEMPERATURE  # noqa: E402

RAW_PATH = REPOSITORY_ROOT / "eval/results/golden_eval_raw.json"
REPORT_PATH = REPOSITORY_ROOT / "eval/results/golden_eval_report.md"


class InvalidGoldenArtifactError(ValueError):
    """Raised when a report would give authority to stale or partial evidence."""


def _validate_run_metadata(document: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not isinstance(document.get("run_id"), str) or not document["run_id"].strip():
        failures.append("run_id must be a non-empty string")
    timestamps: dict[str, datetime] = {}
    for field_name in ("started_at", "finished_at"):
        try:
            parsed = datetime.fromisoformat(document[field_name])
            if parsed.utcoffset() is None:
                raise ValueError
            timestamps[field_name] = parsed
        except (KeyError, TypeError, ValueError):
            failures.append(f"{field_name} must be an aware ISO timestamp")
    if (
        len(timestamps) == 2
        and timestamps["finished_at"] < timestamps["started_at"]
    ):
        failures.append("finished_at precedes started_at")
    if not isinstance(document.get("model"), str) or not document["model"].strip():
        failures.append("model must be a non-empty string")
    if document.get("evidence_level") != "live_llm":
        failures.append("evidence_level must identify a live_llm run")
    if document.get("model_mode") != "live":
        failures.append("model_mode must identify a live provider")
    if document.get("tool_backend") != "fake":
        failures.append("tool_backend must identify deterministic fake tools")
    if document.get("system_boundary") != [
        "provider",
        "agent_graph",
        "fake_tools",
        "scorer",
    ]:
        failures.append("system_boundary is malformed")
    if document.get("environment") != "local":
        failures.append("environment must identify the local golden harness")
    temperature = document.get("temperature")
    if (
        not isinstance(temperature, (int, float))
        or isinstance(temperature, bool)
        or not math.isfinite(float(temperature))
        or float(temperature) != EFFECTIVE_LLM_TEMPERATURE
    ):
        failures.append("temperature does not match the effective model configuration")
    max_steps = document.get("max_steps")
    if type(max_steps) is not int or not 1 <= max_steps <= 8:
        failures.append("max_steps must be an integer from 1 to 8")
    timeout = document.get("timeout_seconds")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not math.isfinite(float(timeout))
        or float(timeout) <= 0
    ):
        failures.append("timeout_seconds must be a finite positive number")
    repetition_count = document.get("repetition_count")
    if type(repetition_count) is not int or repetition_count < 1:
        failures.append("repetition_count must be a positive integer")

    code_hashes = document.get("code_sha256")
    required_paths = {
        "src/agents/prompts.py",
        "src/agents/graph.py",
        "src/services/llm.py",
        "eval/golden_cases.py",
        "eval/live_harness.py",
        "tests/test_agents/test_golden_live.py",
    }
    valid_hashes = isinstance(code_hashes, dict) and required_paths <= set(code_hashes)
    if valid_hashes:
        valid_hashes = all(
            isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
            for value in code_hashes.values()
        )
    if not valid_hashes:
        failures.append("code_sha256 is missing required source hashes")
    else:
        encoded = json.dumps(code_hashes, sort_keys=True).encode("utf-8")
        expected_bundle = hashlib.sha256(encoded).hexdigest()
        if document.get("execution_bundle_sha256") != expected_bundle:
            failures.append("execution bundle hash does not match code_sha256")

    git = document.get("git")
    dirty_state = git.get("working_tree_dirty") if isinstance(git, dict) else "invalid"
    if (
        not isinstance(git, dict)
        or not isinstance(git.get("commit"), str)
        or not isinstance(git.get("branch"), str)
        or (dirty_state is not None and type(dirty_state) is not bool)
    ):
        failures.append("git provenance is malformed")
    return failures


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def validate_artifact(document: dict[str, Any]) -> list[dict[str, Any]]:
    expected_names = [case.name for case in GOLDEN_CASES]
    cases_by_name = {case.name: case for case in GOLDEN_CASES}
    failures: list[str] = []
    failures.extend(_validate_run_metadata(document))
    if document.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        failures.append(f"schema_version must be {ARTIFACT_SCHEMA_VERSION}")
    if document.get("complete") is not True:
        failures.append("run is partial")
    if document.get("run_status") != "complete":
        failures.append("run_status is not complete")
    if document.get("scoring_valid") is not True:
        failures.append("scoring_valid is not true")
    if document.get("dataset_version") != GOLDEN_DATASET_VERSION:
        failures.append("dataset version does not match the current evaluator")
    if document.get("dataset_sha256") != dataset_sha256():
        failures.append("dataset hash does not match the current evaluator")

    results = document.get("results")
    if not isinstance(results, list):
        failures.append("results must be a list")
        results = []
    repetition_count = document.get("repetition_count")
    valid_repetition_count = type(repetition_count) is int and repetition_count > 0
    expected_executions = (
        [
            (name, repetition)
            for repetition in range(repetition_count)
            for name in expected_names
        ]
        if valid_repetition_count
        else []
    )
    result_names = [str(item.get("name", "")) for item in results if isinstance(item, dict)]
    result_executions = [
        (str(item.get("name", "")), item.get("repetition"))
        for item in results
        if isinstance(item, dict)
    ]
    if document.get("expected_case_count") != len(expected_names):
        failures.append("expected case count is wrong")
    if document.get("expected_case_names") != expected_names:
        failures.append("expected case names are stale or reordered")
    if document.get("executed_case_count") != len(expected_names):
        failures.append("executed case count is incomplete")
    if document.get("expected_execution_count") != len(expected_executions):
        failures.append("expected execution count is wrong")
    if document.get("executed_execution_count") != len(expected_executions):
        failures.append("executed execution count is incomplete")
    if len(result_executions) != len(set(result_executions)):
        failures.append("result case/repetition identities are duplicated")
    if set(result_executions) != set(expected_executions):
        failures.append("results do not exactly match every case/repetition execution")
    if set(result_names) != set(expected_names):
        failures.append("result names do not exactly match the golden dataset")

    for result in results:
        if not isinstance(result, dict):
            failures.append("each result must be an object")
            continue
        case = cases_by_name.get(result.get("name"))
        if case is None:
            continue
        repetition = result.get("repetition")
        if (
            valid_repetition_count
            and type(repetition) is int
            and not 0 <= repetition < repetition_count
        ):
            failures.append(f"result {case.name!r}: repetition is out of range")
        failures.extend(
            f"result {case.name!r}: {failure}"
            for failure in validate_result_record(result, case)
        )

    if failures:
        raise InvalidGoldenArtifactError("; ".join(failures))
    return results


def _rate(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator:.1%} ({numerator}/{denominator})" if denominator else "N/A"


def build_report(document: dict[str, Any]) -> str:
    results = validate_artifact(document)
    total = len(results)
    passed = sum(bool(item["passed"]) for item in results)
    tool_passed = sum(bool(item["tool_compliant"]) for item in results)
    response_items = [item for item in results if item["response_evaluable"]]
    response_passed = sum(bool(item["response_compliant"]) for item in response_items)
    refusal_items = [
        item for item in results if item.get("contract", {}).get("expect_refusal") is True
    ]
    refusal_passed = sum(item.get("refusal_compliant") is True for item in refusal_items)
    unauthorized_writes = sum(bool(item["unauthorized_write"]) for item in results)
    forbidden_reads = sum(bool(item["forbidden_read"]) for item in results)
    # Only the graded turn counts toward latency; prior turns exist to build
    # checkpoint state and are reported separately so the two are never mixed.
    durations = [float(item["duration_s"]) for item in results]
    multi_turn = [item for item in results if int(item["graded_turn_index"]) > 0]
    conversation_durations = [float(item["conversation_duration_s"]) for item in multi_turn]
    multi_turn_passed = sum(bool(item["passed"]) for item in multi_turn)

    by_category: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_category.setdefault(str(result["category"]), []).append(result)

    git = document.get("git", {})
    hashes = document.get("code_sha256", {})
    lines = [
        "# ParkSmart Agent — Golden Live-LLM Graph/Model Evaluation",
        "",
        "## Evidence",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Run ID | `{document['run_id']}` |",
        f"| Started / finished (UTC) | `{document['started_at']}` / `{document['finished_at']}` |",
        f"| Model | `{document['model']}` |",
        f"| Temperature | `{document['temperature']}` |",
        f"| Evidence / model / tools | `{document['evidence_level']}` / "
        f"`{document['model_mode']}` / `{document['tool_backend']}` |",
        f"| Agent max steps / timeout | `{document['max_steps']}` / "
        f"`{document['timeout_seconds']}s` |",
        f"| Live repetitions | `{document['repetition_count']}` |",
        f"| Case executions | `{document['executed_execution_count']}` "
        f"({document['expected_case_count']} cases × {document['repetition_count']}) |",
        f"| Git commit | `{git.get('commit', 'unknown')}` |",
        f"| Git branch | `{git.get('branch', 'unknown')}` |",
        f"| Working tree dirty | `{git.get('working_tree_dirty')}` |",
        f"| Dataset | `{document['dataset_version']}` / `{document['dataset_sha256']}` |",
        "| Scope | LangGraph/model output with deterministic fake tools; not API/DB E2E |",
        f"| Execution bundle hash | `{document['execution_bundle_sha256']}` |",
        f"| Prompt hash | `{hashes.get('src/agents/prompts.py', 'unknown')}` |",
        f"| Scorer hash | `{hashes.get('eval/live_harness.py', 'unknown')}` |",
        f"| Runner hash | "
        f"`{hashes.get('tests/test_agents/test_golden_live.py', 'unknown')}` |",
        "",
        "## Summary",
        "",
        f"- Task success: {_rate(passed, total)}",
        f"- Tool-contract accuracy: {_rate(tool_passed, total)}",
        f"- Response-contract accuracy: {_rate(response_passed, len(response_items))}",
        f"- Refusal compliance: {_rate(refusal_passed, len(refusal_items))}",
        f"- Unauthorized write-tool invocation: {_rate(unauthorized_writes, total)}",
        f"- Forbidden/premature read invocation: {_rate(forbidden_reads, total)}",
        f"- Mean in-process golden-harness graded-turn latency: "
        f"{statistics.mean(durations):.2f}s",
        f"- P95 in-process golden-harness graded-turn latency: "
        f"{_percentile(durations, 0.95):.2f}s",
        f"- Multi-turn cases (excluded from the two figures above as whole "
        f"conversations): {_rate(multi_turn_passed, len(multi_turn))} task success; "
        f"{len(multi_turn)}/{total} executions"
        + (
            f"; mean / P95 full-conversation time "
            f"{statistics.mean(conversation_durations):.2f}s / "
            f"{_percentile(conversation_durations, 0.95):.2f}s"
            if conversation_durations
            else ""
        ),
        "",
        "## By category",
        "",
        "| Category | Passed | Total | Rate |",
        "|---|---:|---:|---:|",
    ]
    for category, items in sorted(by_category.items()):
        category_passed = sum(bool(item["passed"]) for item in items)
        lines.append(
            f"| {category} | {category_passed} | {len(items)} | "
            f"{category_passed / len(items):.1%} |"
        )

    lines.extend(
        [
            "",
            "## By repetition",
            "",
            "| Repetition | Passed | Total | Rate |",
            "|---:|---:|---:|---:|",
        ]
    )
    for repetition in range(int(document["repetition_count"])):
        items = [item for item in results if item["repetition"] == repetition]
        repetition_passed = sum(bool(item["passed"]) for item in items)
        lines.append(
            f"| {repetition + 1} | {repetition_passed} | {len(items)} | "
            f"{repetition_passed / len(items):.1%} |"
        )

    failures = [item for item in results if not item["passed"]]
    lines.extend(["", "## Failures", ""])
    if failures:
        for failure in failures:
            reasons = "; ".join(failure.get("reasons", []))
            lines.append(
                f"- **{failure['name']}** repetition {int(failure['repetition']) + 1} "
                f"({failure['category']}): {reasons}"
            )
    else:
        lines.append("None — all cases passed this run.")

    lines.extend(
        [
            "",
            "## Metric interpretation",
            "",
            "- **Accuracy:** task success plus exact tool name/arguments/count/order.",
            "- **Relevance and groundedness:** response contracts are reported only for cases "
            "with a deterministic textual oracle; the denominator is shown explicitly.",
            "- **Safety:** unauthorized write calls and forbidden/premature reads are separate "
            "because their operational impact differs.",
            "- **Latency:** in-process graph/model latency with deterministic fake tools, not "
            "FastAPI/DB production E2E latency. It is measured on the graded turn only; prior "
            "turns build checkpoint state and are reported separately.",
            "- **Response surface:** this evaluates the graph's final AI message. The REST "
            "endpoint's deterministic route/fallback projection requires separate API tests.",
            "- **Critical mutations:** correctness is enforced by deterministic tool name, "
            "arguments, count, turn and dependency-order contracts. No LLM-as-judge is used "
            "to approve a reservation, cancellation, parking confirmation or other write.",
            "- **RAGAS:** not applicable to this repository because the agent has no retrieval "
            "or knowledge-base stage. Tool-grounded contracts measure the available context path.",
            "- A live model is not fully deterministic, even at temperature zero. Preserve each "
            "complete run and compare repeated runs before claiming a stable improvement.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    if not RAW_PATH.exists():
        raise SystemExit(f"{RAW_PATH} not found; run the complete live golden eval first")
    document = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SystemExit("legacy bare-list artifact is invalid; rerun evaluator v2")
    try:
        report = build_report(document)
    except InvalidGoldenArtifactError as error:
        raise SystemExit(f"invalid golden artifact: {error}") from error
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
