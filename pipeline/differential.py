"""Differential testing between a black-box reference and a candidate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Iterable, Sequence

from .execution import ExecutionResult, run_program


class ComparisonStatus(str, Enum):
    PASS = "pass"
    OUTPUT_MISMATCH = "output_mismatch"
    REFERENCE_TIMEOUT = "reference_timeout"
    REFERENCE_ERROR = "reference_error"
    CANDIDATE_TIMEOUT = "candidate_timeout"
    CANDIDATE_ERROR = "candidate_error"


@dataclass(frozen=True)
class DifferentialResult:
    test_input: str
    reference: ExecutionResult
    candidate: ExecutionResult
    status: ComparisonStatus

    @property
    def passed(self) -> bool:
        return self.status is ComparisonStatus.PASS

    def to_dict(self) -> dict:
        return {
            "input": self.test_input,
            "reference": self.reference.to_dict(),
            "candidate": self.candidate.to_dict(),
            "status": self.status.value,
            "passed": self.passed,
        }


def compare_results(
    test_input: str,
    reference: ExecutionResult,
    candidate: ExecutionResult,
) -> DifferentialResult:
    """Classify one pair of executions using exact stdout equality."""

    if reference.timed_out:
        status = ComparisonStatus.REFERENCE_TIMEOUT
    elif not reference.succeeded:
        status = ComparisonStatus.REFERENCE_ERROR
    elif candidate.timed_out:
        status = ComparisonStatus.CANDIDATE_TIMEOUT
    elif not candidate.succeeded:
        status = ComparisonStatus.CANDIDATE_ERROR
    elif candidate.stdout != reference.stdout:
        status = ComparisonStatus.OUTPUT_MISMATCH
    else:
        status = ComparisonStatus.PASS

    return DifferentialResult(
        test_input=test_input,
        reference=reference,
        candidate=candidate,
        status=status,
    )


def run_differential_case(
    reference_command: Sequence[str],
    candidate_command: Sequence[str],
    test_input: str,
    *,
    timeout_seconds: float = 2.0,
    reference_cwd: str | Path | None = None,
    candidate_cwd: str | Path | None = None,
) -> DifferentialResult:
    """Run one testcase against both programs and classify the result."""

    reference = run_program(
        reference_command,
        test_input,
        timeout_seconds=timeout_seconds,
        cwd=reference_cwd,
    )
    candidate = run_program(
        candidate_command,
        test_input,
        timeout_seconds=timeout_seconds,
        cwd=candidate_cwd,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8",
        },
        inherit_env=False,
    )
    return compare_results(test_input, reference, candidate)


def run_differential_suite(
    reference_command: Sequence[str],
    candidate_command: Sequence[str],
    test_inputs: Iterable[str],
    *,
    timeout_seconds: float = 2.0,
    reference_cwd: str | Path | None = None,
    candidate_cwd: str | Path | None = None,
) -> list[DifferentialResult]:
    """Run an iterable of testcases sequentially."""

    return [
        run_differential_case(
            reference_command,
            candidate_command,
            test_input,
            timeout_seconds=timeout_seconds,
            reference_cwd=reference_cwd,
            candidate_cwd=candidate_cwd,
        )
        for test_input in test_inputs
    ]


def write_results(path: str | Path, results: Iterable[DifferentialResult]) -> None:
    """Persist differential results as human-readable JSON."""

    payload = [result.to_dict() for result in results]
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
