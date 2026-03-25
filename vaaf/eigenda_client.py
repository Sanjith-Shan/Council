"""
Council — EigenDA Client
--------------------------
Disperses verification receipt hashes to EigenDA's Holesky testnet
for immutable on-chain proof that every council evaluation happened.

Uses the public disperser at disperser-holesky.eigenda.xyz:443.
No API key required for testnet.

Setup: python vaaf/eigenda_setup.py  (run once to compile proto stubs)
"""

import json
import hashlib
import asyncio
import os
from datetime import datetime
from pathlib import Path


# Try importing compiled proto stubs
_GRPC_AVAILABLE = False
try:
    import grpc
    from vaaf.proto.disperser import disperser_pb2, disperser_pb2_grpc
    _GRPC_AVAILABLE = True
except ImportError:
    pass

EIGENDA_DISPERSER = "disperser-holesky.eigenda.xyz:443"
EIGENDA_LOG_FILE = "eigenda_submissions.jsonl"


class EigenDAClient:
    """Client for dispersing data to EigenDA Holesky testnet."""

    def __init__(self, disperser_url: str = EIGENDA_DISPERSER):
        self.disperser_url = disperser_url
        self.log_path = Path(EIGENDA_LOG_FILE)
        self.submissions: list[dict] = []
        self._load_existing()

    @property
    def is_available(self) -> bool:
        return _GRPC_AVAILABLE

    async def disperse_receipt(self, receipt: dict) -> dict:
        """Disperse a verification receipt hash to EigenDA.

        Returns:
            {"success": True, "request_id": "...", "blob_hash": "..."}
            or {"success": False, "error": "..."}
        """
        # Create the blob data: the receipt hash + metadata
        blob_data = json.dumps({
            "type": "council_verification_receipt",
            "version": "1.0",
            "receipt_hash": receipt.get("hash", ""),
            "action_id": receipt.get("action_id", ""),
            "tier": receipt.get("tier", ""),
            "timestamp": receipt.get("timestamp", ""),
            "chain_prev": receipt.get("prev_hash", ""),
        }, sort_keys=True).encode("utf-8")

        if not _GRPC_AVAILABLE:
            return await self._disperse_fallback(blob_data, receipt)

        try:
            return await self._disperse_grpc(blob_data, receipt)
        except Exception as e:
            error_msg = str(e)[:200]
            # Log the failed attempt
            submission = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "receipt_hash": receipt.get("hash", ""),
                "action_id": receipt.get("action_id", ""),
                "status": "failed",
                "error": error_msg,
                "disperser": self.disperser_url,
            }
            self._persist(submission)
            return {"success": False, "error": error_msg}

    async def _disperse_grpc(self, blob_data: bytes, receipt: dict) -> dict:
        """Disperse via gRPC to the real EigenDA testnet."""
        # Pad data to minimum size (EigenDA requires certain encoding)
        # For small blobs, pad to 32 bytes minimum
        if len(blob_data) < 32:
            blob_data = blob_data + b'\x00' * (32 - len(blob_data))

        # Run gRPC call in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._grpc_disperse_sync, blob_data)

        submission = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "receipt_hash": receipt.get("hash", ""),
            "action_id": receipt.get("action_id", ""),
            "status": "dispersed" if result.get("success") else "failed",
            "request_id": result.get("request_id", ""),
            "blob_hash": hashlib.sha256(blob_data).hexdigest(),
            "disperser": self.disperser_url,
            "error": result.get("error", ""),
        }
        self._persist(submission)
        self.submissions.append(submission)
        return result

    def _grpc_disperse_sync(self, blob_data: bytes) -> dict:
        """Synchronous gRPC dispersal call."""
        try:
            # Create secure channel (EigenDA disperser uses TLS)
            credentials = grpc.ssl_channel_credentials()
            channel = grpc.secure_channel(self.disperser_url, credentials)
            stub = disperser_pb2_grpc.DisperserStub(channel)

            # Create disperse request
            request = disperser_pb2.DisperseBlobRequest(data=blob_data)

            # Call with timeout
            response = stub.DisperseBlob(request, timeout=30)

            request_id = response.request_id.hex() if response.request_id else ""

            channel.close()

            return {
                "success": True,
                "request_id": request_id,
                "blob_hash": hashlib.sha256(blob_data).hexdigest(),
                "result": str(response.result) if hasattr(response, 'result') else "PROCESSING",
            }
        except grpc.RpcError as e:
            return {
                "success": False,
                "error": f"gRPC error: {e.code()} - {e.details()[:100]}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Disperse error: {str(e)[:150]}",
            }

    async def get_blob_status(self, request_id: str) -> dict:
        """Check the status of a previously dispersed blob."""
        if not _GRPC_AVAILABLE:
            return {"status": "unknown", "error": "gRPC not available"}

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._grpc_status_sync, bytes.fromhex(request_id)
            )
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)[:200]}

    def _grpc_status_sync(self, request_id_bytes: bytes) -> dict:
        """Synchronous gRPC status check."""
        try:
            credentials = grpc.ssl_channel_credentials()
            channel = grpc.secure_channel(self.disperser_url, credentials)
            stub = disperser_pb2_grpc.DisperserStub(channel)

            request = disperser_pb2.BlobStatusRequest(request_id=request_id_bytes)
            response = stub.GetBlobStatus(request, timeout=10)

            channel.close()

            status_val = response.status if hasattr(response, 'status') else -1
            status_names = {
                0: "UNKNOWN", 1: "PROCESSING", 2: "CONFIRMED",
                3: "FAILED", 4: "FINALIZED", 5: "INSUFFICIENT_SIGNATURES",
            }

            return {
                "status": status_names.get(status_val, f"STATUS_{status_val}"),
                "raw_status": status_val,
            }
        except grpc.RpcError as e:
            return {"status": "error", "error": f"{e.code()}: {e.details()[:100]}"}

    async def _disperse_fallback(self, blob_data: bytes, receipt: dict) -> dict:
        """Fallback when gRPC stubs aren't compiled.
        Logs the submission and provides instructions.
        """
        blob_hash = hashlib.sha256(blob_data).hexdigest()
        submission = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "receipt_hash": receipt.get("hash", ""),
            "action_id": receipt.get("action_id", ""),
            "status": "pending_setup",
            "blob_hash": blob_hash,
            "disperser": self.disperser_url,
            "note": "Run 'python vaaf/eigenda_setup.py' to enable live EigenDA dispersal",
        }
        self._persist(submission)
        self.submissions.append(submission)
        return {
            "success": False,
            "error": "gRPC not configured. Run: python vaaf/eigenda_setup.py",
            "blob_hash": blob_hash,
        }

    def get_recent_submissions(self, limit: int = 20) -> list[dict]:
        return self.submissions[-limit:]

    def get_stats(self) -> dict:
        total = len(self.submissions)
        dispersed = sum(1 for s in self.submissions if s.get("status") == "dispersed")
        failed = sum(1 for s in self.submissions if s.get("status") == "failed")
        pending = sum(1 for s in self.submissions if s.get("status") == "pending_setup")
        return {
            "total_submissions": total,
            "dispersed": dispersed,
            "failed": failed,
            "pending_setup": pending,
            "disperser": self.disperser_url,
            "grpc_available": _GRPC_AVAILABLE,
        }

    def _persist(self, submission: dict):
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(submission) + "\n")

    def _load_existing(self):
        if not self.log_path.exists():
            return
        try:
            with self.log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self.submissions.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            pass
