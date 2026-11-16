"""
Audit logging - append-only CSV log for all significant system events.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


AUDIT_FIELDS = [
    "event_id", "timestamp", "query_id", "ticket_id",
    "event_type", "intent", "complexity", "priority",
    "knowledge_article_id", "match_score", "route",
    "reviewer_action", "ticket_status",
    "notification_status", "error_details"
]


class AuditLogger:
    def __init__(self, log_path="audit_log.csv"):
        self.path = Path(log_path)

    def log(self, event_type, query_id="", ticket_id="", **kwargs):
        """Append a single audit event."""
        exists = self.path.exists()
        row = {
            "event_id": "EVT-" + uuid4().hex[:8].upper(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query_id": query_id,
            "ticket_id": ticket_id,
            "event_type": event_type,
        }
        for field in AUDIT_FIELDS:
            if field not in row:
                row[field] = kwargs.get(field, "")

        with self.path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=AUDIT_FIELDS, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            writer.writerow(row)
        return row

    def get_logs(self):
        """Read all audit log entries."""
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def get_logs_for_ticket(self, ticket_id):
        return [e for e in self.get_logs() if e.get("ticket_id") == ticket_id]

    def get_logs_for_query(self, query_id):
        return [e for e in self.get_logs() if e.get("query_id") == query_id]
