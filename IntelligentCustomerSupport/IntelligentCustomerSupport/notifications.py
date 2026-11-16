"""
Notification service with retry logic.
Generates, approves, and dispatches notifications. Logs to CSV.
"""

import csv
import time
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path


NOTIFICATION_LOG = "notification_log.csv"
LOG_FIELDS = [
    "notification_id", "ticket_id", "event", "recipient",
    "message", "status", "attempts", "timestamp", "error"
]


def generate_notification(ticket, event):
    """Create a DRAFT notification for a ticket event."""
    tid = ticket.get("ticket_id", "UNKNOWN")
    templates = {
        "CREATED": f"Support ticket {tid} has been created.",
        "ASSIGNED": f"Ticket {tid} has been assigned to {ticket.get('assigned_team', 'a team')}.",
        "ESCALATED": f"Ticket {tid} requires specialist review.",
        "RESOLVED": f"Ticket {tid} has been marked as resolved.",
        "SLA_BREACH": f"Ticket {tid} has exceeded its SLA target.",
        "SLA_AT_RISK": f"Ticket {tid} is approaching its SLA deadline.",
    }
    return {
        "notification_id": "NTF-" + uuid4().hex[:8].upper(),
        "ticket_id": tid,
        "event": event,
        "recipient": ticket.get("customer_id", ""),
        "message": templates.get(event, f"Ticket {tid} has been updated."),
        "status": "DRAFT",
        "attempts": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": ""
    }


def approve_notification(notification, approver_id):
    """Mark a notification as approved for dispatch."""
    notification["status"] = "APPROVED"
    notification["approved_by"] = approver_id
    return notification


def simulate_send(notification):
    """Simulate sending. Returns True on success, False on failure.
    For testing, notifications to recipient 'FAIL_TEST' always fail."""
    if notification.get("recipient") == "FAIL_TEST":
        return False
    if not notification.get("recipient"):
        return False
    return True


def send_with_retry(notification, max_attempts=3):
    """Attempt delivery with exponential backoff.
    Only approved notifications are dispatched."""
    if notification.get("status") != "APPROVED":
        notification["status"] = "NOT_SENT"
        notification["error"] = "Not approved for dispatch"
        return notification

    if not notification.get("recipient"):
        notification["status"] = "FAILED"
        notification["error"] = "No recipient"
        notification["attempts"] = 0
        return notification

    for attempt in range(1, max_attempts + 1):
        notification["attempts"] = attempt
        success = simulate_send(notification)
        if success:
            notification["status"] = "SENT"
            notification["error"] = ""
            return notification
        if attempt < max_attempts:
            time.sleep(0)  # no real delay in lab

    notification["status"] = "FAILED"
    notification["error"] = "All retry attempts exhausted"
    return notification


def log_notification(notification, log_path=None):
    """Append notification record to CSV log."""
    path = Path(log_path or NOTIFICATION_LOG)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(notification)


def dispatch_notification(ticket, event, auto_approve=False, max_attempts=3, log_path=None):
    """Full pipeline: generate -> optionally approve -> send with retry -> log."""
    notif = generate_notification(ticket, event)
    if auto_approve:
        approve_notification(notif, "SYSTEM")
    result = send_with_retry(notif, max_attempts)
    log_notification(result, log_path)
    return result
