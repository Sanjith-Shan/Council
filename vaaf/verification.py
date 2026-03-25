from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from vaaf.models import CouncilResult, CouncilVote, ProposedAction, Tier


class VerificationChain:
    """In-memory + append-only log of council evaluation receipts."""

    def __init__(
        self,
        log_path: str | Path = "verification_log.jsonl",
        db: Any | None = None,
    ):
        self.log_path = Path(log_path)
        self.db = db
        self.chain: list[dict] = []
        self.prev_hash = "0" * 64
        self._load_existing()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_receipt(
        self,
        action: ProposedAction,
        council_result: CouncilResult | None,
        tier: Tier,
        risk_profile,
    ) -> dict:
        """Create a signed receipt for the evaluated action."""
        if hasattr(risk_profile, "model_dump"):
            profile_payload = risk_profile.model_dump()
        elif isinstance(risk_profile, dict):
            profile_payload = risk_profile
        else:
            profile_payload = getattr(risk_profile, "__dict__", str(risk_profile))

        profile_json = json.dumps(profile_payload, sort_keys=True, default=str)

        receipt = {
            "action_id": action.id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "tool_name": action.tool_name,
            "description_hash": hashlib.sha256(action.description.encode("utf-8")).hexdigest()[:16],
            "council_votes": self._serialize_votes(council_result),
            "final_verdict": (council_result.final_verdict.value if council_result else "pre_filtered"),
            "tier": tier.value,
            "profile_hash": hashlib.sha256(profile_json.encode("utf-8")).hexdigest()[:16],
            "prev_hash": self.prev_hash,
        }

        receipt_bytes = json.dumps(receipt, sort_keys=True).encode("utf-8")
        receipt_hash = hashlib.sha256(receipt_bytes).hexdigest()
        receipt["hash"] = receipt_hash
        self.prev_hash = receipt_hash
        self.chain.append(receipt)
        self._persist(receipt)
        return receipt

    def verify(self) -> dict:
        """Verify chain integrity by recomputing hashes."""
        if not self.chain:
            return {"valid": True, "receipts_checked": 0, "chain_intact": True}

        prev = "0" * 64
        for idx, receipt in enumerate(self.chain):
            expected_prev = receipt.get("prev_hash")
            if expected_prev != prev:
                return {
                    "valid": False,
                    "receipts_checked": idx,
                    "chain_intact": False,
                    "break_at": idx,
                }

            stored_hash = receipt.get("hash")
            shadow = {k: v for k, v in receipt.items() if k != "hash"}
            computed = hashlib.sha256(json.dumps(shadow, sort_keys=True).encode("utf-8")).hexdigest()
            if computed != stored_hash:
                return {
                    "valid": False,
                    "receipts_checked": idx,
                    "chain_intact": False,
                    "break_at": idx,
                }

            prev = stored_hash

        return {"valid": True, "receipts_checked": len(self.chain), "chain_intact": True}

    def get_recent(self, limit: int = 20) -> list[dict]:
        if limit <= 0:
            return []
        return [receipt.copy() for receipt in self.chain[-limit:]]

    def get_receipt(self, action_id: str) -> dict | None:
        for receipt in reversed(self.chain):
            if receipt.get("action_id") == action_id:
                return receipt.copy()
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _serialize_votes(self, council_result: CouncilResult | None) -> list[dict]:
        if not council_result:
            return []
        votes: Iterable[CouncilVote] = council_result.votes
        return [
            {
                "checker": vote.checker,
                "verdict": vote.verdict.value,
                "reason": vote.reason,
                "confidence": vote.confidence,
            }
            for vote in votes
        ]

    def _persist(self, receipt: dict):
        if not self.log_path.parent.exists():
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt) + "\n")
        if self.db and hasattr(self.db, "append_verification_receipt"):
            self.db.append_verification_receipt(receipt)
        # Production: submit receipt.hash to EigenDA via AgentKit SDK for immutable on-chain storage

    def _load_existing(self):
        if not self.log_path.exists():
            return
        try:
            with self.log_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        receipt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self.chain.append(receipt)
                    self.prev_hash = receipt.get("hash", self.prev_hash)
        except OSError:
            # If the log cannot be read, start a fresh chain while keeping genesis hash
            self.chain = []
            self.prev_hash = "0" * 64
