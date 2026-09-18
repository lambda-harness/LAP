"""Executable ``lap-effect/0.1`` external-effect lifecycle tests."""

from __future__ import annotations

import unittest
from typing import cast

from lap_protocol.artifact_ledger import ArtifactScope
from lap_protocol.effect_ledger import (
    EffectAuthorizationError,
    EffectConflictError,
    EffectLedger,
    EffectRule,
    EffectStateError,
    EffectTerminalConflictError,
    EffectTerminalGateError,
    EffectValidationError,
)

SCOPE = ArtifactScope("tenant-reference", "run-reference")
CAPABILITY = "release.execute"
EFFECT_TYPE = "jenkins.release"
OTHER_EFFECT_TYPE = "inventory.publish"
REQUEST_DIGEST = "sha256:" + "1" * 64
OTHER_DIGEST = "sha256:" + "2" * 64


def intent_payload(
    *,
    intent_id: str = "intent-1",
    effect_type: str = EFFECT_TYPE,
    request_digest: str = REQUEST_DIGEST,
    summary: str = "Publish the approved release.",
) -> dict[str, str]:
    """Build one strict effect-intent payload fixture."""
    return {
        "intent_id": intent_id,
        "effect_type": effect_type,
        "request_digest": request_digest,
        "summary": summary,
    }


class EffectLedgerTests(unittest.TestCase):
    """Verify Host authority and truthful external-effect outcomes."""

    def setUp(self) -> None:
        """Create one capability-scoped Host effect ledger for each test."""
        self.ledger = EffectLedger(
            SCOPE,
            CAPABILITY,
            (
                EffectRule(EFFECT_TYPE, True, False),
                EffectRule(OTHER_EFFECT_TYPE, False, False),
            ),
        )

    def test_required_effect_acceptance_is_not_settlement(self) -> None:
        """Keep successful Run admission behind verified business completion."""
        proposed = self.ledger.propose("intent-event", intent_payload())
        authorized = self.ledger.authorize(
            "authorized-event",
            proposed.effect_id,
            authorization_ref="authorization-1",
        )
        accepted = self.ledger.accept(
            "accepted-event",
            proposed.effect_id,
            provider_operation_ref="provider-operation-1",
        )

        self.assertEqual(proposed.state, "proposed")
        self.assertEqual(authorized.state, "authorized")
        self.assertEqual(accepted.state, "accepted")
        self.assertFalse(accepted.is_terminal)
        self.assertFalse(accepted.retry_permitted)
        with self.assertRaises(EffectTerminalGateError) as unresolved:
            self.ledger.validate_success()
        self.assertEqual(unresolved.exception.code, "LAP-104")

        settled = self.ledger.record_settled(
            "settled-event", proposed.effect_id, evidence_ref="receipt-1"
        )
        self.assertEqual(settled.state, "settled")
        self.assertTrue(settled.is_terminal)
        self.assertFalse(settled.needs_reconciliation)
        self.assertEqual(self.ledger.validate_success(), (settled,))
        self.assertEqual(
            [transition.event_type for transition in self.ledger.transitions()],
            [
                "effect.intent",
                "effect.authorized",
                "effect.accepted",
                "effect.settled",
            ],
        )

    def test_approval_reference_is_required_before_authorization(self) -> None:
        """Require a matching Host approval without treating it as a provider call."""
        approval_ledger = EffectLedger(
            SCOPE, CAPABILITY, (EffectRule(EFFECT_TYPE, True, True, max_intents=2),)
        )
        proposed = approval_ledger.propose("intent-event", intent_payload())
        awaiting_approval = approval_ledger.request_approval(
            "approval-request-event", proposed.effect_id, approval_ref="approval-1"
        )
        self.assertEqual(awaiting_approval.state, "approval_required")

        with self.assertRaises(EffectStateError):
            approval_ledger.authorize(
                "missing-approval-event",
                proposed.effect_id,
                authorization_ref="authorization-1",
            )
        with self.assertRaises(EffectStateError):
            approval_ledger.authorize(
                "wrong-approval-event",
                proposed.effect_id,
                authorization_ref="authorization-1",
                approval_ref="approval-other",
            )

        authorized = approval_ledger.authorize(
            "authorized-event",
            proposed.effect_id,
            authorization_ref="authorization-1",
            approval_ref="approval-1",
        )
        self.assertEqual(authorized.state, "authorized")
        self.assertEqual(authorized.approval_ref, "approval-1")

        denied = approval_ledger.propose(
            "second-intent-event", intent_payload(intent_id="intent-2")
        )
        approval_ledger.request_approval(
            "second-approval-event", denied.effect_id, approval_ref="approval-2"
        )
        denied_terminal = approval_ledger.deny_approval(
            "approval-denied-event",
            denied.effect_id,
            approval_ref="approval-2",
            summary="The release window is closed.",
        )
        self.assertEqual(denied_terminal.state, "failed")
        self.assertEqual(denied_terminal.failure_code, "LAP-301")
        self.assertIsNone(denied_terminal.provider_operation_ref)

    def test_unknown_effect_requires_reconciliation_and_never_auto_retries(
        self,
    ) -> None:
        """Retain unknown execution evidence instead of guessing or repeating it."""
        proposed = self.ledger.propose("intent-event", intent_payload())
        self.ledger.authorize(
            "authorized-event",
            proposed.effect_id,
            authorization_ref="authorization-1",
        )
        self.ledger.accept(
            "accepted-event",
            proposed.effect_id,
            provider_operation_ref="provider-operation-1",
        )
        unknown = self.ledger.record_unknown(
            "unknown-event", proposed.effect_id, observation_ref="observation-1"
        )
        self.assertEqual(unknown.state, "unknown")
        self.assertTrue(unknown.needs_reconciliation)
        self.assertFalse(unknown.retry_permitted)

        reconciling = self.ledger.begin_reconciliation(
            "reconciling-event",
            proposed.effect_id,
            reconciliation_ref="reconciliation-1",
        )
        terminal = self.ledger.resolve_reconciliation(
            "indeterminate-event",
            proposed.effect_id,
            outcome="indeterminate",
            evidence_ref="reconciliation-result-1",
            failure_code="LAP-500",
            failure_summary="The provider outcome cannot be proven.",
        )
        self.assertEqual(reconciling.state, "reconciling")
        self.assertEqual(terminal.state, "indeterminate")
        self.assertTrue(terminal.is_terminal)
        self.assertTrue(terminal.needs_reconciliation)
        self.assertFalse(terminal.retry_permitted)
        with self.assertRaises(EffectTerminalGateError):
            self.ledger.validate_success()

        with self.assertRaises(EffectTerminalConflictError):
            self.ledger.record_settled(
                "late-settle-event", proposed.effect_id, evidence_ref="late-receipt"
            )
        with self.assertRaises(EffectTerminalConflictError):
            self.ledger.record_settled(
                "late-settle-event", proposed.effect_id, evidence_ref="late-receipt"
            )
        with self.assertRaises(EffectConflictError):
            self.ledger.record_settled(
                "late-settle-event",
                proposed.effect_id,
                evidence_ref="changed-late-receipt",
            )
        self.assertEqual(len(self.ledger.anomalies()), 1)
        self.assertEqual(
            self.ledger.anomalies()[0].reason,
            "terminal_effect_record_already_exists",
        )

    def test_intent_and_event_idempotency_reject_changed_data(self) -> None:
        """Keep repeated logical intent safe while rejecting mutated replays."""
        first = self.ledger.propose("intent-event", intent_payload())
        self.assertIs(self.ledger.propose("intent-event", intent_payload()), first)
        same_intent = self.ledger.propose("duplicate-intent-event", intent_payload())
        self.assertEqual(same_intent.effect_id, first.effect_id)
        self.assertEqual(self.ledger.snapshot().effect_count, 1)
        self.assertEqual(self.ledger.snapshot().transition_count, 1)

        with self.assertRaises(EffectConflictError):
            self.ledger.propose(
                "intent-event",
                intent_payload(summary="A changed request."),
            )
        with self.assertRaises(EffectConflictError):
            self.ledger.propose(
                "changed-intent-event",
                intent_payload(request_digest=OTHER_DIGEST),
            )

    def test_optional_failed_effect_does_not_claim_settlement_or_block_required_gate(
        self,
    ) -> None:
        """Allow explicitly optional evidence to fail without becoming success proof."""
        optional = self.ledger.propose(
            "optional-intent-event",
            intent_payload(
                intent_id="optional-intent",
                effect_type=OTHER_EFFECT_TYPE,
                request_digest=OTHER_DIGEST,
            ),
        )
        self.ledger.authorize(
            "optional-authorized-event",
            optional.effect_id,
            authorization_ref="authorization-optional",
        )
        self.ledger.accept(
            "optional-accepted-event",
            optional.effect_id,
            provider_operation_ref="provider-operation-optional",
        )
        failed = self.ledger.record_failed(
            "optional-failed-event",
            optional.effect_id,
            evidence_ref="failure-receipt-optional",
            failure_code="LAP-500",
            failure_summary="The optional notification did not complete.",
        )
        self.assertEqual(failed.state, "failed")
        self.assertFalse(failed.retry_permitted)
        self.assertEqual(self.ledger.validate_success(), ())
        payload = failed.payload()
        self.assertNotIn("authorization_ref", payload)
        self.assertNotIn("approval_ref", payload)
        self.assertEqual(payload["failure_code"], "LAP-500")

    def test_policy_and_payload_validation_fail_before_external_execution(self) -> None:
        """Reject unsafe Host policy and malformed Agent intents before acceptance."""
        with self.assertRaises(EffectValidationError):
            EffectLedger(
                cast(ArtifactScope, "not-a-scope"),
                CAPABILITY,
                (EffectRule(EFFECT_TYPE, True, False),),
            )
        with self.assertRaises(EffectValidationError):
            EffectLedger(SCOPE, CAPABILITY, EFFECT_TYPE)
        with self.assertRaises(EffectValidationError):
            EffectLedger(
                SCOPE,
                CAPABILITY,
                (
                    EffectRule(EFFECT_TYPE, True, False),
                    EffectRule(EFFECT_TYPE, True, False),
                ),
            )
        with self.assertRaises(EffectAuthorizationError):
            self.ledger.propose(
                "unauthorized-effect-event",
                intent_payload(effect_type="database.delete"),
            )
        with self.assertRaises(EffectValidationError):
            self.ledger.propose(
                "malformed-intent-event",
                {"intent_id": "intent-1"},
            )
        proposed = self.ledger.propose("valid-intent-event", intent_payload())
        with self.assertRaises(EffectValidationError):
            self.ledger.resolve_reconciliation(
                "bad-outcome-event",
                proposed.effect_id,
                outcome="settled",
                evidence_ref="evidence-1",
                failure_code="LAP-500",
                failure_summary="Unexpected failure metadata.",
            )
        with self.assertRaises(EffectStateError):
            self.ledger.record_settled(
                "settled-before-accept-event",
                proposed.effect_id,
                evidence_ref="evidence-1",
            )


if __name__ == "__main__":
    unittest.main()
