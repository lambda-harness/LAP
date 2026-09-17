"""Executable Core 0.2 reference Artifact receipt and terminal-gating tests."""

from __future__ import annotations

import hashlib
import unittest
from collections.abc import Collection
from typing import Any, cast

from lap_protocol.artifact_ledger import (
    ArtifactConflictError,
    ArtifactIntegrityError,
    ArtifactLedger,
    ArtifactPolicyError,
    ArtifactQuotaError,
    ArtifactScope,
    ArtifactTerminalError,
    ArtifactValidationError,
)

CONTENT = b"verified spreadsheet bytes"
SHA256 = hashlib.sha256(CONTENT).hexdigest()
SCOPE = ArtifactScope(tenant_id="tenant-reference", run_id="run-reference")


def offer_payload(
    *,
    artifact_id: str = "invoice-workbook",
    content: bytes = CONTENT,
    required: bool = True,
) -> dict[str, Any]:
    """Build one valid Core 0.2 Artifact Offer fixture."""

    return {
        "artifact_id": artifact_id,
        "name": "invoices.xlsx",
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "source_ref": "lap://run/output/invoices.xlsx",
        "delivery": {
            "kind": "download",
            "required": required,
            "disposition": "attachment",
            "scope": "session",
            "retention": {"class": "standard"},
        },
        "semantic": {"role": "final_result", "title": "Invoice workbook"},
    }


class Core02ArtifactLedgerTests(unittest.TestCase):
    """Verify portable Artifact semantics without claiming a Host object store."""

    def test_commits_required_artifact_and_gates_success_by_receipt(self) -> None:
        ledger = ArtifactLedger(SCOPE)
        ledger.offer(offer_payload())

        with self.assertRaises(ArtifactTerminalError):
            ledger.validate_success([])

        receipt = ledger.commit("invoice-workbook", CONTENT)
        selected = ledger.validate_success([receipt.receipt_id])
        self.assertEqual(selected, (receipt,))
        self.assertEqual(receipt.scope, SCOPE)
        self.assertEqual(receipt.sha256, SHA256)
        self.assertEqual(receipt.size_bytes, len(CONTENT))
        self.assertEqual(receipt.canonical_ref, f"lap://artifact/{receipt.receipt_id}")
        self.assertNotIn("source_ref", receipt.payload())
        self.assertNotIn("invoices.xlsx", receipt.canonical_ref)

    def test_offer_and_commit_are_idempotent_but_changed_identity_conflicts(
        self,
    ) -> None:
        ledger = ArtifactLedger(SCOPE)
        first_offer = ledger.offer(offer_payload())
        repeated_offer = ledger.offer(offer_payload())
        first_receipt = ledger.commit("invoice-workbook", CONTENT)
        repeated_receipt = ledger.commit("invoice-workbook", CONTENT)

        self.assertEqual(first_offer, repeated_offer)
        self.assertEqual(first_receipt, repeated_receipt)
        changed = offer_payload(content=b"different bytes")
        with self.assertRaises(ArtifactConflictError) as raised:
            ledger.offer(changed)
        self.assertEqual(raised.exception.code, "LAP-109")

    def test_integrity_failure_creates_no_receipt_or_deliverable(self) -> None:
        ledger = ArtifactLedger(SCOPE)
        ledger.offer(offer_payload())
        with self.assertRaises(ArtifactIntegrityError):
            ledger.commit("invoice-workbook", b"wrong")
        with self.assertRaises(ArtifactIntegrityError):
            ledger.commit("invoice-workbook", b"x" * len(CONTENT))
        self.assertIsNone(ledger.receipt_for("invoice-workbook"))
        with self.assertRaises(ArtifactTerminalError):
            ledger.validate_success([])

    def test_optional_artifacts_do_not_block_success_but_known_receipts_are_valid(
        self,
    ) -> None:
        ledger = ArtifactLedger(SCOPE)
        ledger.offer(offer_payload(required=False))
        self.assertEqual(ledger.validate_success([]), ())

        receipt = ledger.commit("invoice-workbook", CONTENT)
        self.assertEqual(ledger.validate_success([receipt.receipt_id]), (receipt,))

    def test_policy_and_quota_rejections_happen_before_commit(self) -> None:
        too_small = ArtifactLedger(SCOPE, max_artifact_bytes=len(CONTENT) - 1)
        with self.assertRaises(ArtifactQuotaError):
            too_small.offer(offer_payload())

        media_limited = ArtifactLedger(SCOPE, allowed_media_types={"application/pdf"})
        with self.assertRaises(ArtifactPolicyError):
            media_limited.offer(offer_payload())

        delivery_limited = ArtifactLedger(
            SCOPE,
            supported_delivery_kinds={"reference"},
            supported_delivery_scopes={"run"},
        )
        with self.assertRaises(ArtifactPolicyError):
            delivery_limited.offer(offer_payload())

        scope_limited = ArtifactLedger(
            SCOPE,
            supported_delivery_kinds={"download"},
            supported_delivery_scopes={"run"},
        )
        with self.assertRaises(ArtifactPolicyError):
            scope_limited.offer(offer_payload())

        one_artifact = ArtifactLedger(SCOPE, max_artifacts=1)
        one_artifact.offer(offer_payload())
        with self.assertRaises(ArtifactQuotaError):
            one_artifact.offer(offer_payload(artifact_id="preview"))

    def test_rejects_malformed_metadata_without_private_path_acceptance(self) -> None:
        cases: list[tuple[str, dict[str, Any]]] = []
        missing = offer_payload()
        del missing["semantic"]
        cases.append(("missing field", missing))
        name = offer_payload()
        name["name"] = "nested/invoices.xlsx"
        cases.append(("path name", name))
        media = offer_payload()
        media["media_type"] = "Application/XLSX"
        cases.append(("media type", media))
        source = offer_payload()
        source["source_ref"] = "file:///private/output.xlsx"
        cases.append(("private source", source))
        digest = offer_payload()
        digest["sha256"] = digest["sha256"].upper()
        cases.append(("uppercase digest", digest))
        delivery = offer_payload()
        delivery["delivery"]["disposition"] = "inline"
        cases.append(("download disposition", delivery))
        semantic = offer_payload()
        semantic["semantic"]["role"] = "unknown"
        cases.append(("semantic role", semantic))

        ledger = ArtifactLedger(SCOPE)
        for label, candidate in cases:
            with self.subTest(case=label):
                with self.assertRaises(ArtifactValidationError):
                    ledger.offer(candidate)

    def test_success_rejects_unknown_duplicate_and_out_of_scope_receipts(self) -> None:
        ledger = ArtifactLedger(SCOPE)
        ledger.offer(offer_payload())
        receipt = ledger.commit("invoice-workbook", CONTENT)
        with self.assertRaises(ArtifactTerminalError):
            ledger.validate_success(["receipt-unknown"])
        with self.assertRaises(ArtifactTerminalError):
            ledger.validate_success([receipt.receipt_id, receipt.receipt_id])
        with self.assertRaises(ArtifactTerminalError):
            ledger.validate_success("receipt-not-a-collection")

    def test_offer_metadata_is_defensive_and_receipt_lookups_are_scoped(self) -> None:
        payload = offer_payload()
        payload["delivery"]["required"] = False
        payload["semantic"]["source_count"] = 3
        ledger = ArtifactLedger(SCOPE)
        offer = ledger.offer(payload)
        payload["delivery"]["scope"] = "tenant"
        self.assertEqual(offer.delivery["scope"], "session")
        self.assertFalse(offer.required)
        self.assertEqual(offer.semantic["source_count"], 3)
        returned_delivery = offer.delivery
        returned_delivery["scope"] = "run"
        self.assertEqual(offer.delivery["scope"], "session")
        returned_semantic = offer.semantic
        returned_semantic["source_count"] = 0
        self.assertEqual(offer.semantic["source_count"], 3)
        self.assertEqual(offer.payload()["name"], "invoices.xlsx")
        receipt = ledger.commit("invoice-workbook", CONTENT)
        self.assertEqual(ledger.receipt_for("invoice-workbook"), receipt)

        other = ArtifactLedger(ArtifactScope("tenant-other", "run-reference"))
        with self.assertRaises(ArtifactTerminalError):
            other.validate_success([receipt.receipt_id])
        self.assertIsNone(other.receipt_for("invoice-workbook"))

    def test_rejects_invalid_construction_and_content_types(self) -> None:
        with self.assertRaises(ArtifactValidationError):
            ArtifactLedger(cast(ArtifactScope, "not-a-scope"))
        with self.assertRaises(ArtifactValidationError):
            ArtifactLedger(SCOPE, max_artifacts=0)
        with self.assertRaises(ArtifactValidationError):
            ArtifactLedger(SCOPE, max_artifacts=True)
        with self.assertRaises(ArtifactValidationError):
            ArtifactLedger(SCOPE, max_artifact_bytes=-1)
        with self.assertRaises(ArtifactValidationError):
            ArtifactLedger(SCOPE, allowed_media_types="application/pdf")
        with self.assertRaises(ArtifactValidationError):
            ArtifactLedger(SCOPE, allowed_media_types=cast(Collection[str], []))
        with self.assertRaises(ArtifactValidationError):
            ArtifactLedger(SCOPE, supported_delivery_kinds=cast(Collection[str], None))
        with self.assertRaises(ArtifactValidationError):
            ArtifactLedger(SCOPE, supported_delivery_scopes={""})

        ledger = ArtifactLedger(SCOPE)
        with self.assertRaises(ArtifactValidationError):
            ledger.commit("unknown", CONTENT)
        ledger.offer(offer_payload())
        with self.assertRaises(ArtifactValidationError):
            ledger.commit("invoice-workbook", cast(bytes, bytearray(CONTENT)))

    def test_rejects_non_json_offer_values_and_invalid_opaque_identifiers(self) -> None:
        ledger = ArtifactLedger(SCOPE)
        with self.assertRaises(ArtifactValidationError):
            ledger.offer(cast(dict[str, Any], []))
        with self.assertRaises(ArtifactValidationError):
            ArtifactScope("", "run-reference")
        with self.assertRaises(ArtifactValidationError):
            ArtifactScope("tenant-reference", "\ud800")
        with self.assertRaises(ArtifactValidationError):
            ledger.receipt_for("")

        invalid_id = offer_payload()
        invalid_id["artifact_id"] = "\ud800"
        with self.assertRaises(ArtifactValidationError):
            ledger.offer(invalid_id)

        oversized_name = offer_payload()
        oversized_name["name"] = "x" * 241
        with self.assertRaises(ArtifactValidationError):
            ledger.offer(oversized_name)

        boolean_size = offer_payload()
        boolean_size["size_bytes"] = True
        with self.assertRaises(ArtifactValidationError):
            ledger.offer(boolean_size)

    def test_rejects_delivery_and_semantic_contract_violations(self) -> None:
        cases: list[tuple[str, dict[str, Any]]] = []
        invalid_kind = offer_payload()
        invalid_kind["delivery"]["kind"] = "webhook"
        cases.append(("delivery kind", invalid_kind))
        invalid_required = offer_payload()
        invalid_required["delivery"]["required"] = "true"
        cases.append(("delivery required", invalid_required))
        invalid_disposition = offer_payload()
        invalid_disposition["delivery"]["disposition"] = "preview"
        cases.append(("delivery disposition", invalid_disposition))
        inline_mismatch = offer_payload()
        inline_mismatch["delivery"]["kind"] = "inline"
        cases.append(("inline disposition", inline_mismatch))
        invalid_scope = offer_payload()
        invalid_scope["delivery"]["scope"] = "workspace"
        cases.append(("delivery scope", invalid_scope))
        missing_retention_class = offer_payload()
        missing_retention_class["delivery"]["retention"] = {}
        cases.append(("retention class", missing_retention_class))
        invalid_expiry = offer_payload()
        invalid_expiry["delivery"]["retention"]["expires_at"] = ""
        cases.append(("retention expiry", invalid_expiry))
        extra_semantic_field = offer_payload()
        extra_semantic_field["semantic"]["internal_path"] = "C:/private"
        cases.append(("semantic fields", extra_semantic_field))
        invalid_title = offer_payload()
        invalid_title["semantic"]["title"] = ""
        cases.append(("semantic title", invalid_title))
        boolean_source_count = offer_payload()
        boolean_source_count["semantic"]["source_count"] = True
        cases.append(("semantic source count", boolean_source_count))

        ledger = ArtifactLedger(SCOPE)
        for label, candidate in cases:
            with self.subTest(case=label):
                with self.assertRaises(ArtifactValidationError):
                    ledger.offer(candidate)

    def test_success_requires_a_collection_of_known_receipts(self) -> None:
        ledger = ArtifactLedger(SCOPE)
        with self.assertRaises(ArtifactTerminalError):
            ledger.validate_success(cast(Collection[str], 1))


if __name__ == "__main__":
    unittest.main()
