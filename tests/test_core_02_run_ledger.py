"""Executable Core 0.2 reference Run terminal and structured-error tests."""

from __future__ import annotations

import hashlib
import threading
import unittest
from typing import Any, cast

from lap_protocol.artifact_ledger import (
    ArtifactLedger,
    ArtifactScope,
    ArtifactTerminalError,
)
from lap_protocol.run_ledger import (
    RunConflictError,
    RunLedger,
    RunResult,
    RunStateError,
    RunTerminalConflictError,
    RunValidationError,
    SafeError,
    TerminalRecord,
)

CONTENT = b"run-ledger-deliverable"
SCOPE = ArtifactScope(tenant_id="tenant-reference", run_id="run-reference")


def artifact_offer(*, required: bool = True) -> dict[str, Any]:
    """Build one valid Core 0.2 Artifact offer fixture."""

    return {
        "artifact_id": "workbook",
        "name": "result.xlsx",
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "size_bytes": len(CONTENT),
        "sha256": hashlib.sha256(CONTENT).hexdigest(),
        "source_ref": "lap://run/output/result.xlsx",
        "delivery": {
            "kind": "download",
            "required": required,
            "disposition": "attachment",
            "scope": "session",
            "retention": {"class": "standard"},
        },
        "semantic": {"role": "final_result", "title": "Result workbook"},
    }


def safe_error(*, retryable: bool = False) -> dict[str, Any]:
    """Build one fully populated Core safe-error fixture."""

    return {
        "code": "LAP-201",
        "message": "The external outcome needs reconciliation.",
        "retryable": retryable,
        "phase": "reconciliation",
        "json_pointer": "/targets/0",
        "constraint": "required",
        "cause_code": "OUTCOME_UNPROVEN",
        "responsibility": "profile",
        "operator_correlation_id": "operator-correlation",
        "recovery": {"action": "reconcile", "retry_after_ms": 500},
    }


def successful_result(receipt_ids: list[str] | None = None) -> dict[str, Any]:
    """Build one valid successful Core `run.result` fixture."""

    payload: dict[str, Any] = {
        "status": "succeeded",
        "summary": "Workbook is ready.",
        "output": {"rows": 3},
    }
    if receipt_ids is not None:
        payload["artifact_receipt_ids"] = receipt_ids
    return payload


def failed_result(receipt_ids: list[str] | None = None) -> dict[str, Any]:
    """Build one valid failed Core `run.result` fixture."""

    payload: dict[str, Any] = {
        "status": "failed",
        "summary": "Validation did not complete.",
        "error": safe_error(retryable=True),
    }
    if receipt_ids is not None:
        payload["artifact_receipt_ids"] = receipt_ids
    return payload


def running_ledger(*, artifact_ledger: ArtifactLedger | None = None) -> RunLedger:
    """Create one Run ledger that has completed start and acceptance."""

    ledger = RunLedger(SCOPE, artifact_ledger=artifact_ledger)
    ledger.start("start-event")
    ledger.accept("accepted-event")
    return ledger


class Core02RunLedgerTests(unittest.TestCase):
    """Verify first-terminal-wins and structured Core result semantics."""

    def test_success_waits_for_required_receipt_and_ack_is_idempotent(self) -> None:
        artifacts = ArtifactLedger(SCOPE)
        artifacts.offer(artifact_offer(required=True))
        ledger = running_ledger(artifact_ledger=artifacts)

        with self.assertRaises(ArtifactTerminalError):
            ledger.record_result("result-event", successful_result([]))
        self.assertEqual(ledger.state, "running")

        receipt = artifacts.commit("workbook", CONTENT)
        terminal = ledger.record_result(
            "result-event", successful_result([receipt.receipt_id])
        )
        acknowledgement = ledger.acknowledge_terminal("ack-event")

        self.assertEqual(terminal.status, "succeeded")
        self.assertFalse(terminal.retry_permitted)
        self.assertFalse(terminal.requires_reconciliation)
        self.assertEqual(terminal.result.output, {"rows": 3})
        self.assertEqual(ledger.state, "succeeded")
        self.assertEqual(
            acknowledgement.payload()["ledger_record_id"], terminal.ledger_record_id
        )
        self.assertTrue(acknowledgement.recorded_at.endswith("Z"))
        self.assertIs(
            ledger.record_result(
                "result-event", successful_result([receipt.receipt_id])
            ),
            terminal,
        )
        self.assertIs(ledger.acknowledge_terminal("ack-event"), acknowledgement)

    def test_non_success_artifacts_still_require_known_same_scope_receipts(
        self,
    ) -> None:
        artifacts = ArtifactLedger(SCOPE)
        artifacts.offer(artifact_offer(required=False))
        receipt = artifacts.commit("workbook", CONTENT)
        ledger = running_ledger(artifact_ledger=artifacts)

        terminal = ledger.record_result(
            "failed-event", failed_result([receipt.receipt_id])
        )
        self.assertEqual(terminal.status, "failed")
        self.assertTrue(terminal.retry_permitted)

        second = running_ledger(artifact_ledger=artifacts)
        with self.assertRaises(ArtifactTerminalError):
            second.record_result("unknown-receipt", failed_result(["receipt-unknown"]))
        self.assertEqual(second.state, "running")

        without_artifacts = running_ledger()
        with self.assertRaises(RunValidationError):
            without_artifacts.record_result(
                "missing-ledger", failed_result([receipt.receipt_id])
            )

    def test_lifecycle_transitions_replay_exact_events_and_reject_bad_states(
        self,
    ) -> None:
        ledger = RunLedger(SCOPE)
        with self.assertRaises(RunStateError):
            ledger.accept("accepted-before-start")

        start = ledger.start("start-event")
        self.assertEqual(start.prior_state, "queued")
        self.assertEqual(start.state, "starting")
        self.assertIs(ledger.start("start-event"), start)
        with self.assertRaises(RunConflictError):
            ledger.accept("start-event")

        ledger.accept("accepted-event")
        requested = ledger.request_input("input-request", "request-1")
        self.assertEqual(requested.state, "input_required")
        resumed = ledger.respond_input("input-response", "request-1")
        self.assertEqual(resumed.state, "running")
        reconciling = ledger.begin_reconciliation("reconciling", "Provider timed out.")
        self.assertEqual(reconciling.state, "reconciling")
        cancel_request = ledger.request_cancel("cancel-request", "User cancelled.")
        self.assertEqual(cancel_request.prior_state, "reconciling")
        self.assertEqual(cancel_request.state, "reconciling")
        self.assertEqual(ledger.snapshot().transition_count, 6)

    def test_concurrent_cancel_and_result_write_exactly_one_terminal_record(
        self,
    ) -> None:
        ledger = running_ledger()
        gate = threading.Barrier(3)
        outcomes: list[object] = []
        outcomes_lock = threading.Lock()

        def record_result() -> None:
            """Try one terminal result on the shared Run ledger."""
            gate.wait()
            try:
                outcome: object = ledger.record_result(
                    "result-event", successful_result()
                )
            except RunTerminalConflictError as exc:
                outcome = exc
            with outcomes_lock:
                outcomes.append(outcome)

        def record_cancelled() -> None:
            """Try one Agent cancellation confirmation on the shared Run ledger."""
            gate.wait()
            try:
                outcome: object = ledger.record_cancelled(
                    "cancelled-event", reason="Cancellation confirmed."
                )
            except RunTerminalConflictError as exc:
                outcome = exc
            with outcomes_lock:
                outcomes.append(outcome)

        result_thread = threading.Thread(target=record_result)
        cancel_thread = threading.Thread(target=record_cancelled)
        result_thread.start()
        cancel_thread.start()
        gate.wait()
        result_thread.join()
        cancel_thread.join()

        terminals = [
            outcome for outcome in outcomes if isinstance(outcome, TerminalRecord)
        ]
        conflicts = [
            outcome
            for outcome in outcomes
            if isinstance(outcome, RunTerminalConflictError)
        ]
        self.assertEqual(len(terminals), 1)
        self.assertEqual(len(conflicts), 1)
        self.assertIs(ledger.terminal(), terminals[0])
        self.assertEqual(len(ledger.anomalies()), 1)

    def test_late_terminal_anomaly_is_retained_once_without_rewriting_history(
        self,
    ) -> None:
        ledger = running_ledger()
        terminal = ledger.record_result("result-event", successful_result())

        with self.assertRaises(RunTerminalConflictError):
            ledger.record_cancelled("late-event", reason="Late cancellation.")
        with self.assertRaises(RunTerminalConflictError):
            ledger.record_cancelled("late-event", reason="Late cancellation.")
        with self.assertRaises(RunConflictError):
            ledger.record_cancelled("late-event", reason="Changed late cancellation.")

        self.assertIs(ledger.terminal(), terminal)
        anomalies = ledger.anomalies()
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0].reason, "terminal_record_already_exists")
        self.assertEqual(ledger.snapshot().anomaly_count, 1)

    def test_indeterminate_requires_reconciliation_and_cannot_be_blindly_retried(
        self,
    ) -> None:
        ledger = running_ledger()
        ledger.begin_reconciliation("reconciling", "Provider acknowledgement was lost.")
        payload = {
            "status": "indeterminate",
            "summary": "The provider outcome cannot be proven.",
            "error": safe_error(retryable=True),
        }

        terminal = ledger.record_result("indeterminate-event", payload)
        self.assertEqual(terminal.status, "indeterminate")
        self.assertTrue(terminal.requires_reconciliation)
        self.assertFalse(terminal.retry_permitted)
        self.assertEqual(
            terminal.result.error,
            SafeError.from_payload(safe_error(retryable=True)),
        )
        self.assertIn("terminal_status", terminal.payload())

    def test_safe_error_is_defensive_and_rejects_invalid_contract_fields(self) -> None:
        payload = safe_error(retryable=True)
        error = SafeError.from_payload(payload)
        payload["recovery"]["action"] = "changed"
        self.assertEqual(error.code, "LAP-201")
        self.assertTrue(error.retryable)
        self.assertEqual(error.payload()["recovery"]["action"], "reconcile")

        invalid_cases: list[dict[str, Any]] = []
        invalid_code = safe_error()
        invalid_code["code"] = "ERROR"
        invalid_cases.append(invalid_code)
        invalid_responsibility = safe_error()
        invalid_responsibility["responsibility"] = "operator"
        invalid_cases.append(invalid_responsibility)
        invalid_recovery = safe_error()
        invalid_recovery["recovery"]["retry_after_ms"] = True
        invalid_cases.append(invalid_recovery)
        invalid_utf8 = safe_error()
        invalid_utf8["message"] = "\ud800"
        invalid_cases.append(invalid_utf8)
        extra = safe_error()
        extra["private_path"] = "C:/private/output"
        invalid_cases.append(extra)

        for candidate in invalid_cases:
            with self.subTest(candidate=candidate):
                with self.assertRaises(RunValidationError):
                    SafeError.from_payload(candidate)

    def test_result_contract_is_strict_and_output_is_defensive(self) -> None:
        valid = successful_result()
        valid["output"] = {"nested": ["value"]}
        result = RunResult.from_payload(valid)
        valid["output"]["nested"].append("changed")
        decoded = cast(dict[str, Any], result.output)
        decoded["nested"].append("changed-again")
        self.assertEqual(result.output, {"nested": ["value"]})

        invalid_cases: list[dict[str, Any]] = []
        no_output = successful_result()
        del no_output["output"]
        invalid_cases.append(no_output)
        success_error = successful_result()
        success_error["error"] = safe_error()
        invalid_cases.append(success_error)
        no_error = failed_result()
        del no_error["error"]
        invalid_cases.append(no_error)
        duplicate_receipts = successful_result(["receipt-1", "receipt-1"])
        invalid_cases.append(duplicate_receipts)
        non_array_receipts = successful_result()
        non_array_receipts["artifact_receipt_ids"] = cast(Any, ("receipt-1",))
        invalid_cases.append(non_array_receipts)
        non_finite_output = successful_result()
        non_finite_output["output"] = float("nan")
        invalid_cases.append(non_finite_output)
        invalid_utf8_output = successful_result()
        invalid_utf8_output["output"] = "\ud800"
        invalid_cases.append(invalid_utf8_output)

        for candidate in invalid_cases:
            with self.subTest(candidate=candidate):
                with self.assertRaises(RunValidationError):
                    RunResult.from_payload(candidate)

    def test_scope_and_terminal_ack_validation_fail_closed(self) -> None:
        other_scope = ArtifactScope("tenant-other", "run-reference")
        artifacts = ArtifactLedger(other_scope)
        with self.assertRaises(RunValidationError):
            RunLedger(SCOPE, artifact_ledger=artifacts)
        with self.assertRaises(RunValidationError):
            RunLedger(cast(ArtifactScope, "not-a-scope"))

        ledger = RunLedger(SCOPE)
        with self.assertRaises(RunStateError):
            ledger.acknowledge_terminal("ack-before-terminal")
        with self.assertRaises(RunValidationError):
            ledger.start("\ud800")


if __name__ == "__main__":
    unittest.main()
