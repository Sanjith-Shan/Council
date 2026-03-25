"""SQLite persistence layer for Council."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from vaaf.models import (
    ActivityEvent,
    ActionStatus,
    CouncilResult,
    CouncilVote,
    EvaluatedAction,
    ProposedAction,
    RiskProfile,
    Tier,
    Verdict,
)


class CouncilDatabase:
    def __init__(self, db_path: str = "council.db"):
        self.path = Path(db_path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS risk_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def upsert_action(self, action: EvaluatedAction):
        payload = action.model_dump(mode="json")
        self.conn.execute(
            """
            INSERT INTO actions (id, payload_json, status, timestamp)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload_json=excluded.payload_json,
                status=excluded.status,
                timestamp=excluded.timestamp
            """,
            (action.action.id, json.dumps(payload), action.status.value, action.timestamp.isoformat()),
        )
        self.conn.commit()

    def list_actions(self) -> list[EvaluatedAction]:
        rows = self.conn.execute("SELECT payload_json FROM actions ORDER BY timestamp ASC").fetchall()
        return [self._parse_action_row(r[0]) for r in rows]

    def get_action(self, action_id: str) -> EvaluatedAction | None:
        row = self.conn.execute("SELECT payload_json FROM actions WHERE id = ?", (action_id,)).fetchone()
        if not row:
            return None
        return self._parse_action_row(row[0])

    def append_event(self, event: ActivityEvent):
        payload = event.model_dump(mode="json")
        self.conn.execute(
            "INSERT INTO events (id, payload_json, timestamp) VALUES (?, ?, ?)",
            (event.id, json.dumps(payload), event.timestamp.isoformat()),
        )
        self.conn.commit()

    def list_events(self) -> list[ActivityEvent]:
        rows = self.conn.execute("SELECT payload_json FROM events ORDER BY timestamp ASC").fetchall()
        return [self._parse_event_row(r[0]) for r in rows]

    def save_risk_profile(self, profile: RiskProfile):
        payload = profile.model_dump(mode="json")
        self.conn.execute(
            """
            INSERT INTO risk_profile (id, payload_json, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at
            """,
            (json.dumps(payload), datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def load_risk_profile(self) -> RiskProfile | None:
        row = self.conn.execute("SELECT payload_json FROM risk_profile WHERE id = 1").fetchone()
        if not row:
            return None
        return RiskProfile(**json.loads(row[0]))

    def set_user_setting(self, key: str, value):
        self.conn.execute(
            """
            INSERT INTO user_settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
            """,
            (key, json.dumps(value), datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_user_setting(self, key: str, default=None):
        row = self.conn.execute("SELECT value_json FROM user_settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        return json.loads(row[0])

    def _parse_action_row(self, payload_json: str) -> EvaluatedAction:
        payload = json.loads(payload_json)
        action_payload = payload["action"]
        action = ProposedAction(
            id=action_payload["id"],
            tool_name=action_payload["tool_name"],
            description=action_payload["description"],
            parameters=action_payload.get("parameters") or {},
            reasoning=action_payload.get("reasoning", ""),
            timestamp=datetime.fromisoformat(action_payload["timestamp"]),
        )

        council = None
        if payload.get("council_result"):
            cr = payload["council_result"]
            votes = [
                CouncilVote(
                    checker=v["checker"],
                    verdict=Verdict(v["verdict"]),
                    reason=v["reason"],
                    latency_ms=v.get("latency_ms", 0),
                    confidence=v.get("confidence", 0.0),
                )
                for v in cr.get("votes", [])
            ]
            council = CouncilResult(
                votes=votes,
                final_verdict=Verdict(cr["final_verdict"]),
                tier=Tier(cr["tier"]),
                total_latency_ms=cr.get("total_latency_ms", 0),
            )

        return EvaluatedAction(
            action=action,
            council_result=council,
            tier=Tier(payload["tier"]),
            status=ActionStatus(payload["status"]),
            pre_filtered=payload.get("pre_filtered", False),
            first_use_escalated=payload.get("first_use_escalated", False),
            execution_result=payload.get("execution_result"),
            approved_by=payload.get("approved_by"),
            timestamp=datetime.fromisoformat(payload["timestamp"]),
        )

    def _parse_event_row(self, payload_json: str) -> ActivityEvent:
        payload = json.loads(payload_json)
        tier = payload.get("tier")
        return ActivityEvent(
            id=payload["id"],
            event_type=payload["event_type"],
            action_id=payload.get("action_id"),
            summary=payload["summary"],
            details=payload.get("details") or {},
            tier=Tier(tier) if tier else None,
            timestamp=datetime.fromisoformat(payload["timestamp"]),
        )
