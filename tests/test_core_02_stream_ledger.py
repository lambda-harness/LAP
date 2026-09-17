"""Executable Core 0.2 reference stream-ledger invariants."""

from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast

from lap_protocol.stream_ledger import (
    AckRangeError,
    ApplyResult,
    CheckpointError,
    EpochError,
    InvalidStreamEventError,
    ReplayUnavailableError,
    SequenceConflictError,
    SequenceGapError,
    StaleEpochError,
    StreamLedger,
)

STREAM_ID = "stream-reference-0001"


def payload(phase: str) -> dict[str, object]:
    """Build one JSON-safe fixture payload."""

    return {"type": "run.progress", "phase": phase, "nested": {"count": 1}}


class Core02StreamLedgerTests(unittest.TestCase):
    """Verify reference semantics without claiming a Core 0.2 Host adapter."""

    def ledger(
        self,
        *,
        retention_events: int = 256,
        max_replay_events: int | None = None,
    ) -> StreamLedger:
        """Create one test ledger with the first writer lease acquired."""

        result = StreamLedger(
            STREAM_ID,
            retention_events=retention_events,
            max_replay_events=max_replay_events,
        )
        result.acquire_epoch(1)
        return result

    def apply(
        self,
        ledger: StreamLedger,
        sequence: int,
        *,
        epoch: int = 1,
        phase: str | None = None,
    ) -> ApplyResult:
        """Append one stable event fixture."""

        return ledger.apply(
            epoch=epoch,
            seq=sequence,
            event_id=f"event-{epoch}-{sequence}",
            payload=payload(phase or f"phase-{sequence}"),
        )

    def test_applies_strict_sequence_and_acknowledges_only_applied_events(self) -> None:
        ledger = self.ledger()
        self.assertEqual(self.apply(ledger, 1).disposition, "applied")
        self.assertEqual(self.apply(ledger, 2).disposition, "applied")

        advanced = ledger.acknowledge(epoch=1, seq=2)
        duplicate = ledger.acknowledge(epoch=1, seq=1)
        self.assertTrue(advanced.advanced)
        self.assertEqual(advanced.ack_seq, 2)
        self.assertFalse(duplicate.advanced)
        self.assertEqual(duplicate.ack_seq, 2)
        with self.assertRaises(AckRangeError):
            ledger.acknowledge(epoch=1, seq=3)

        snapshot = ledger.snapshot()
        self.assertEqual(snapshot.last_applied_seq, 2)
        self.assertEqual(snapshot.last_acked_seq, 2)
        self.assertTrue(snapshot.replay_available)

    def test_exact_duplicate_is_idempotent_but_a_collision_is_not(self) -> None:
        ledger = self.ledger()
        first = self.apply(ledger, 1)
        duplicate = self.apply(ledger, 1)
        self.assertEqual(first.disposition, "applied")
        self.assertEqual(duplicate.disposition, "duplicate")
        self.assertEqual(first.event.fingerprint, duplicate.event.fingerprint)

        with self.assertRaises(SequenceConflictError):
            ledger.apply(
                epoch=1,
                seq=1,
                event_id="a-different-event",
                payload=payload("phase-1"),
            )
        with self.assertRaises(SequenceConflictError):
            ledger.apply(
                epoch=1,
                seq=1,
                event_id="event-1-1",
                payload=payload("different"),
            )
        self.assertEqual(ledger.snapshot().last_applied_seq, 1)

    def test_gap_pauses_application_until_the_missing_event_arrives(self) -> None:
        ledger = self.ledger()
        self.apply(ledger, 1)
        with self.assertRaises(SequenceGapError):
            self.apply(ledger, 3)
        self.assertEqual(ledger.snapshot().last_applied_seq, 1)
        self.assertEqual(self.apply(ledger, 2).disposition, "applied")
        self.assertEqual(self.apply(ledger, 3).disposition, "applied")

    def test_new_epoch_fences_old_writer_without_sequence_collision(self) -> None:
        ledger = self.ledger()
        self.apply(ledger, 1)
        self.assertEqual(ledger.acquire_epoch(1).epoch, 1)
        self.assertEqual(ledger.acquire_epoch(2).epoch, 2)

        with self.assertRaises(StaleEpochError):
            self.apply(ledger, 2, epoch=1)
        self.assertEqual(self.apply(ledger, 1, epoch=2).disposition, "applied")
        previous = ledger.replay(epoch=1, after_seq=0)
        self.assertEqual([event.seq for event in previous.events], [1])
        self.assertEqual(ledger.snapshot().epoch, 2)

    def test_lost_ack_replay_does_not_apply_a_second_transition(self) -> None:
        ledger = self.ledger()
        first = self.apply(ledger, 1)
        replayed_delivery = self.apply(ledger, 1)
        page = ledger.replay(epoch=1, after_seq=0)

        self.assertEqual(replayed_delivery.disposition, "duplicate")
        self.assertEqual(ledger.snapshot().last_applied_seq, 1)
        self.assertTrue(page.complete)
        self.assertEqual(len(page.events), 1)
        self.assertEqual(page.events[0].fingerprint, first.event.fingerprint)

    def test_bounded_replay_reports_unavailable_without_losing_duplicate_identity(
        self,
    ) -> None:
        ledger = self.ledger(retention_events=2, max_replay_events=1)
        self.apply(ledger, 1)
        self.apply(ledger, 2)
        self.apply(ledger, 3)

        with self.assertRaises(ReplayUnavailableError):
            ledger.replay(epoch=1, after_seq=0)
        first_page = ledger.replay(epoch=1, after_seq=1)
        second_page = ledger.replay(epoch=1, after_seq=first_page.next_after_seq)
        self.assertEqual([event.seq for event in first_page.events], [2])
        self.assertFalse(first_page.complete)
        self.assertEqual([event.seq for event in second_page.events], [3])
        self.assertTrue(second_page.complete)
        self.assertEqual(self.apply(ledger, 1).disposition, "duplicate")

    def test_checkpoint_restores_provable_state_and_fences_prior_epoch(self) -> None:
        ledger = self.ledger()
        self.apply(ledger, 1)
        ledger.acknowledge(epoch=1, seq=1)
        ledger.acquire_epoch(2)
        self.apply(ledger, 1, epoch=2)
        checkpoint = json.loads(json.dumps(ledger.export_state()))

        restored = StreamLedger.from_state(checkpoint)
        self.assertEqual(restored.snapshot().epoch, 2)
        self.assertEqual(restored.snapshot(epoch=1).last_acked_seq, 1)
        self.assertEqual(self.apply(restored, 2, epoch=2).disposition, "applied")
        with self.assertRaises(StaleEpochError):
            self.apply(restored, 2, epoch=1)

    def test_rejects_invalid_leases_bounds_payloads_and_checkpoints(self) -> None:
        with self.assertRaises(InvalidStreamEventError):
            StreamLedger("", retention_events=1)
        with self.assertRaises(InvalidStreamEventError):
            StreamLedger(STREAM_ID, retention_events=1, max_replay_events=2)

        ledger = self.ledger()
        with self.assertRaises(EpochError):
            ledger.acquire_epoch(3)
        with self.assertRaises(InvalidStreamEventError):
            ledger.apply(epoch=1, seq=True, event_id="event", payload=payload("x"))
        with self.assertRaises(InvalidStreamEventError):
            ledger.apply(
                epoch=1, seq=1, event_id="event", payload={"nan": float("nan")}
            )
        with self.assertRaises(InvalidStreamEventError):
            ledger.apply(
                epoch=1,
                seq=1,
                event_id="event",
                payload=cast(Mapping[str, Any], {1: "bad"}),
            )
        self.apply(ledger, 1)
        with self.assertRaises(InvalidStreamEventError):
            ledger.replay(epoch=1, after_seq=0, limit=257)

        checkpoint = ledger.export_state()
        bad_format = deepcopy(checkpoint)
        bad_format["format"] = "other"
        with self.assertRaises(CheckpointError):
            StreamLedger.from_state(bad_format)
        bad_identity = deepcopy(checkpoint)
        bad_identity["epochs"][0]["identities"][0]["fingerprint"] = "0" * 64
        with self.assertRaises(CheckpointError):
            StreamLedger.from_state(bad_identity)

    def test_empty_snapshot_unknown_epoch_and_defensive_event_payload(self) -> None:
        ledger = StreamLedger(STREAM_ID)
        empty = ledger.snapshot()
        self.assertEqual(empty.epoch, 0)
        self.assertTrue(empty.replay_available)
        with self.assertRaises(EpochError):
            self.apply(ledger, 1)
        with self.assertRaises(EpochError):
            ledger.replay(epoch=1, after_seq=0)

        ledger.acquire_epoch(1)
        applied = self.apply(ledger, 1)
        event_payload = applied.event.payload
        event_payload["phase"] = "mutated"
        self.assertEqual(applied.event.payload["phase"], "phase-1")
        self.assertTrue(ledger.replay(epoch=1, after_seq=1).complete)
        with self.assertRaises(InvalidStreamEventError):
            ledger.replay(epoch=1, after_seq=2)

        ledger.acquire_epoch(2)
        delayed = ledger.acknowledge(epoch=1, seq=1)
        self.assertTrue(delayed.advanced)
        self.assertEqual(ledger.snapshot().epoch, 2)


if __name__ == "__main__":
    unittest.main()
