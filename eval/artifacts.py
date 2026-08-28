"""Provenance and validation helpers for golden evaluation artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.golden_cases import (
    ALL_TOOL_NAMES,
    GOLDEN_CASES,
    GOLDEN_DATASET_VERSION,
    GoldenCase,
)
from eval.live_harness import ToolInvocation, score_case

ARTIFACT_SCHEMA_VERSION = 2
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_RESULTS_PATH = REPOSITORY_ROOT / "eval/results/golden_eval_raw.json"
RUN_ARCHIVE_DIR = REPOSITORY_ROOT / "eval/results/runs"
_EXECUTION_SOURCE_PATHS = (
    "src/agents/prompts.py",
    "src/agents/graph.py",
    "src/agents/nodes/assistant.py",
    "src/agents/nodes/guard_input.py",
    "src/agents/nodes/prepare_context.py",
    "src/agents/nodes/observe_tool.py",
    "src/services/llm.py",
    "eval/golden_cases.py",
    "eval/live_harness.py",
    "eval/artifacts.py",
    "tests/test_agents/test_golden_live.py",
)
REQUIRED_RESULT_FIELDS = frozenset(
    {
        "name",
        "category",
        "contract",
        "passed",
        "reasons",
        "tool_compliant",
        "response_compliant",
        "response_evaluable",
        "refusal_compliant",
        "unauthorized_write",
        "forbidden_read",
        "duration_s",
        "turn_durations_s",
        "conversation_duration_s",
        "graded_turn_index",
        "executed_calls",
        "requested_calls",
        "tool_call_rounds",
        "final_text",
    }
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def golden_case_payload(case: GoldenCase) -> dict[str, Any]:
    return {
        "name": case.name,
        "category": case.category,
        "prior_turns": list(case.prior_turns),
        "utterance": case.utterance,
        "scenario": case.scenario.value,
        "expected_calls": [
            {
                "name": item.name,
                "arguments": item.arguments,
                "min_calls": item.min_calls,
                "max_calls": item.max_calls,
                "turn_index": item.turn_index,
            }
            for item in case.expected_calls
        ],
        "allowed_tools": sorted(case.allowed_tools),
        "forbidden_tools": sorted(case.forbidden_tools),
        "ordered_tools": list(case.ordered_tools),
        "must_contain_any": list(case.must_contain_any),
        "must_not_contain": list(case.must_not_contain),
        "must_match": list(case.must_match),
        "must_not_match": list(case.must_not_match),
        "expect_refusal": case.expect_refusal,
        "refusal_requires_no_tools": case.refusal_requires_no_tools,
        "notes": case.notes,
    }


def dataset_sha256() -> str:
    payload = [golden_case_payload(case) for case in GOLDEN_CASES]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return _sha256_bytes(encoded)


def _non_negative_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def validate_result_record(result: dict[str, Any], case: GoldenCase) -> list[str]:
    """Validate and independently rescore one serialized case result."""
    failures: list[str] = []
    missing = REQUIRED_RESULT_FIELDS - set(result)
    if missing:
        return [f"missing fields {sorted(missing)}"]

    if result.get("name") != case.name:
        failures.append("name does not match the golden case")
    if result.get("category") != case.category:
        failures.append("category does not match the golden case")
    if result.get("contract") != golden_case_payload(case):
        failures.append("embedded contract does not match the golden case")

    for field_name in (
        "passed",
        "tool_compliant",
        "response_compliant",
        "response_evaluable",
        "unauthorized_write",
        "forbidden_read",
    ):
        if type(result.get(field_name)) is not bool:
            failures.append(f"{field_name} must be a boolean")
    if result.get("refusal_compliant") is not None and type(
        result.get("refusal_compliant")
    ) is not bool:
        failures.append("refusal_compliant must be a boolean or null")
    reasons = result.get("reasons")
    if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
        failures.append("reasons must be a list of strings")
    final_text = result.get("final_text")
    if not isinstance(final_text, str):
        failures.append("final_text must be a string")

    invocations: list[ToolInvocation] = []
    raw_calls = result.get("executed_calls")
    valid_calls = isinstance(raw_calls, list)
    if valid_calls:
        for index, raw_call in enumerate(raw_calls):
            if (
                not isinstance(raw_call, dict)
                or set(raw_call) != {"name", "arguments", "turn_index"}
                or not isinstance(raw_call.get("name"), str)
                or raw_call.get("name") not in ALL_TOOL_NAMES
                or not isinstance(raw_call.get("arguments"), dict)
                or type(raw_call.get("turn_index")) is not int
                or raw_call.get("turn_index") < 0
            ):
                failures.append(f"executed_calls[{index}] is malformed")
                valid_calls = False
                continue
            invocations.append(
                ToolInvocation(
                    name=raw_call["name"],
                    arguments=raw_call["arguments"],
                    turn_index=raw_call["turn_index"],
                )
            )
    else:
        failures.append("executed_calls must be a list")

    requested_invocations: list[ToolInvocation] = []
    raw_requests = result.get("requested_calls")
    valid_requests = isinstance(raw_requests, list)
    if valid_requests:
        for index, raw_request in enumerate(raw_requests):
            if (
                not isinstance(raw_request, dict)
                or set(raw_request) != {"name", "arguments", "turn_index"}
                or not isinstance(raw_request.get("name"), str)
                or not raw_request.get("name")
                or not isinstance(raw_request.get("arguments"), dict)
                or type(raw_request.get("turn_index")) is not int
                or raw_request.get("turn_index") < 0
            ):
                failures.append(f"requested_calls[{index}] is malformed")
                valid_requests = False
                continue
            requested_invocations.append(
                ToolInvocation(
                    name=raw_request["name"],
                    arguments=raw_request["arguments"],
                    turn_index=raw_request["turn_index"],
                )
            )
    else:
        failures.append("requested_calls must be a list")

    parsed_rounds: list[tuple[str, ...]] = []
    raw_rounds = result.get("tool_call_rounds")
    valid_rounds = isinstance(raw_rounds, list)
    if valid_rounds:
        for index, raw_round in enumerate(raw_rounds):
            if not isinstance(raw_round, list) or not all(
                isinstance(name, str) and bool(name) for name in raw_round
            ):
                failures.append(f"tool_call_rounds[{index}] is malformed")
                valid_rounds = False
                continue
            parsed_rounds.append(tuple(raw_round))
    else:
        failures.append("tool_call_rounds must be a list")

    if valid_calls and valid_requests and valid_rounds:
        executed_counts = Counter(item.name for item in invocations)
        requested_counts = Counter(item.name for item in requested_invocations)
        if any(executed_counts[name] > requested_counts[name] for name in executed_counts):
            failures.append("an executed tool call has no matching assistant request")
        round_counts = Counter(name for names in parsed_rounds for name in names)
        if round_counts != requested_counts:
            failures.append("requested_calls do not match tool_call_rounds")

    duration = result.get("duration_s")
    conversation_duration = result.get("conversation_duration_s")
    raw_turn_durations = result.get("turn_durations_s")
    graded_turn_index = result.get("graded_turn_index")
    expected_turn_count = len(case.prior_turns) + 1
    if not _non_negative_number(duration):
        failures.append("duration_s must be a finite non-negative number")
    if not _non_negative_number(conversation_duration):
        failures.append("conversation_duration_s must be a finite non-negative number")
    valid_turn_durations = isinstance(raw_turn_durations, list) and all(
        _non_negative_number(value) for value in raw_turn_durations
    )
    if not valid_turn_durations:
        failures.append("turn_durations_s must contain finite non-negative numbers")
    elif len(raw_turn_durations) != expected_turn_count:
        failures.append("turn_durations_s length does not match the conversation")
    if type(graded_turn_index) is not int or graded_turn_index != expected_turn_count - 1:
        failures.append("graded_turn_index does not identify the final user turn")
    if valid_turn_durations and raw_turn_durations:
        if _non_negative_number(duration) and abs(
            float(duration) - float(raw_turn_durations[-1])
        ) > 0.001:
            failures.append("duration_s does not match the graded turn duration")
        if _non_negative_number(conversation_duration) and float(
            conversation_duration
        ) + 0.01 < sum(float(value) for value in raw_turn_durations):
            failures.append("conversation_duration_s is shorter than its turns")

    can_rescore = (
        valid_calls
        and valid_requests
        and valid_rounds
        and isinstance(final_text, str)
        and isinstance(reasons, list)
        and all(isinstance(item, str) for item in reasons)
    )
    if can_rescore:
        rescored = score_case(
            case,
            invocations,
            final_text,
            call_rounds=parsed_rounds,
            requested_calls=requested_invocations,
        )
        expected_fields = {
            "passed": rescored.passed,
            "reasons": list(rescored.reasons),
            "tool_compliant": rescored.tool_compliant,
            "response_compliant": rescored.response_compliant,
            "response_evaluable": rescored.response_evaluable,
            "refusal_compliant": rescored.refusal_compliant,
            "unauthorized_write": rescored.unauthorized_write,
            "forbidden_read": rescored.forbidden_read,
        }
        for field_name, expected_value in expected_fields.items():
            if result.get(field_name) != expected_value:
                failures.append(f"{field_name} does not match independent rescoring")
    return failures


def _git(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={REPOSITORY_ROOT.as_posix()}", *args],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def git_provenance() -> dict[str, Any]:
    status = _git("status", "--porcelain")
    return {
        "commit": _git("rev-parse", "HEAD") or "unknown",
        "branch": _git("branch", "--show-current") or "unknown",
        "working_tree_dirty": None if status is None else bool(status),
    }


def execution_provenance() -> dict[str, Any]:
    code_hashes = {
        relative_path: file_sha256(REPOSITORY_ROOT / relative_path)
        for relative_path in _EXECUTION_SOURCE_PATHS
    }
    bundle = json.dumps(code_hashes, sort_keys=True).encode("utf-8")
    return {
        "git": git_provenance(),
        "code_sha256": code_hashes,
        "execution_bundle_sha256": _sha256_bytes(bundle),
    }


def _atomic_json_write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


@dataclass(slots=True)
class GoldenRunRecorder:
    """Collect one pytest run without letting a partial run replace the baseline."""

    model: str
    temperature: float
    max_steps: int = 8
    timeout_seconds: float = 30.0
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: str = field(default_factory=_utc_now)
    results: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=execution_provenance, init=False)

    def build_document(self) -> dict[str, Any]:
        expected_names = [case.name for case in GOLDEN_CASES]
        cases_by_name = {case.name: case for case in GOLDEN_CASES}
        result_names = [str(result.get("name", "")) for result in self.results]
        well_formed = all(
            isinstance(result, dict)
            and result.get("name") in cases_by_name
            and not validate_result_record(result, cases_by_name[result["name"]])
            for result in self.results
        )
        complete = (
            len(result_names) == len(expected_names)
            and len(set(result_names)) == len(result_names)
            and set(result_names) == set(expected_names)
            and well_formed
        )
        order = {name: index for index, name in enumerate(expected_names)}
        ordered_results = sorted(
            self.results,
            key=lambda result: order.get(str(result.get("name", "")), len(order)),
        )
        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "scoring_valid": complete,
            "complete": complete,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": _utc_now(),
            "model": self.model,
            "temperature": self.temperature,
            "dataset_version": GOLDEN_DATASET_VERSION,
            "dataset_sha256": dataset_sha256(),
            "max_steps": self.max_steps,
            "timeout_seconds": self.timeout_seconds,
            "code_sha256": self.provenance["code_sha256"],
            "execution_bundle_sha256": self.provenance["execution_bundle_sha256"],
            "git": self.provenance["git"],
            "expected_case_count": len(expected_names),
            "expected_case_names": expected_names,
            "executed_case_count": len(result_names),
            "results": ordered_results,
        }

    def persist(self) -> tuple[Path, Path | None]:
        document = self.build_document()
        stamp = self.started_at.replace("+00:00", "Z").replace(":", "")
        suffix = "complete" if document["complete"] else "partial"
        archive = RUN_ARCHIVE_DIR / f"golden_eval_{stamp}_{self.run_id[:8]}_{suffix}.json"
        _atomic_json_write(archive, document)
        canonical: Path | None = None
        if document["complete"]:
            _atomic_json_write(CANONICAL_RESULTS_PATH, document)
            canonical = CANONICAL_RESULTS_PATH
        return archive, canonical


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "CANONICAL_RESULTS_PATH",
    "GoldenRunRecorder",
    "REQUIRED_RESULT_FIELDS",
    "dataset_sha256",
    "execution_provenance",
    "golden_case_payload",
    "validate_result_record",
]
