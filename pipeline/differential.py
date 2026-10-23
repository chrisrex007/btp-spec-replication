"""Differential testing between a black-box reference and a candidate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .execution import ExecutionResult, run_program
from .artifacts import atomic_json


class ComparisonStatus(str, Enum):
    PASS = "pass"
    OUTPUT_MISMATCH = "output_mismatch"
    REFERENCE_TIMEOUT = "reference_timeout"
    REFERENCE_ERROR = "reference_error"
    CANDIDATE_TIMEOUT = "candidate_timeout"
    CANDIDATE_ERROR = "candidate_error"


class EvaluationInterrupted(Exception):
    """A cooperative stop left the current evaluation suite uncommitted."""


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
    """Compare losslessly decoded stdout, preserving every original byte."""

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
    should_stop: Callable[[], bool] = lambda: False,
) -> list[DifferentialResult]:
    """Run an iterable of testcases sequentially."""

    results = []
    for test_input in test_inputs:
        if should_stop():
            raise EvaluationInterrupted()
        results.append(run_differential_case(
            reference_command,
            candidate_command,
            test_input,
            timeout_seconds=timeout_seconds,
            reference_cwd=reference_cwd,
            candidate_cwd=candidate_cwd,
        ))
    if should_stop():
        raise EvaluationInterrupted()
    return results


def write_results(path: str | Path, results: Iterable[DifferentialResult]) -> None:
    """Persist differential results as human-readable JSON."""

    payload = [result.to_dict() for result in results]
    atomic_json(path, payload)


def summarize_results(results: list[DifferentialResult]) -> dict:
    reference_failures = sum(not result.reference.succeeded for result in results)
    passed = sum(result.passed for result in results)
    valid = len(results) - reference_failures
    return {
        "status": "invalid_reference" if reference_failures else "completed",
        "n_total": len(results), "n_valid": valid,
        "n_reference_failures": reference_failures, "n_pass": passed,
        "n_fail": valid - passed,
        "accuracy": passed / len(results) if results and not reference_failures else None,
        "status_counts": {status.value: sum(r.status is status for r in results)
                          for status in ComparisonStatus if any(r.status is status for r in results)},
    }
