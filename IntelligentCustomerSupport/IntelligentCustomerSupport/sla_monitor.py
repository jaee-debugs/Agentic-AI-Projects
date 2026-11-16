"""
SLA monitoring - checks tickets against their deadlines.
"""

from datetime import datetime, timezone


SLA_STATES = ["WITHIN_SLA", "AT_RISK", "BREACHED", "PAUSED"]

# "at risk" when less than this fraction of time remains
AT_RISK_FRACTION = 0.2


def check_sla(ticket, now=None):
    """Check a single ticket's SLA status.
    Returns dict with sla_state and details."""
    if now is None:
        now = datetime.now(timezone.utc)

    status = ticket.get("status", "")
    if status in ("CLOSED", "RESOLVED"):
        return {"sla_state": "WITHIN_SLA", "detail": "Ticket already resolved/closed"}

    if status in ("ON_HOLD", "PAUSED"):
        return {"sla_state": "PAUSED", "detail": "SLA clock paused"}

    due_str = ticket.get("first_response_due")
    if not due_str:
        return {"sla_state": "WITHIN_SLA", "detail": "No SLA deadline set"}

    due = datetime.fromisoformat(due_str)
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)

    created_str = ticket.get("created_at", "")
    if created_str:
        created = datetime.fromisoformat(created_str)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
    else:
        created = due

    remaining = (due - now).total_seconds()
    total = (due - created).total_seconds()

    if remaining <= 0:
        return {
            "sla_state": "BREACHED",
            "detail": f"Deadline passed by {abs(remaining)/60:.1f} minutes",
            "overdue_minutes": abs(remaining) / 60
        }

    if total > 0 and remaining / total <= AT_RISK_FRACTION:
        return {
            "sla_state": "AT_RISK",
            "detail": f"Only {remaining/60:.1f} minutes remaining",
            "remaining_minutes": remaining / 60
        }

    return {
        "sla_state": "WITHIN_SLA",
        "detail": f"{remaining/60:.1f} minutes remaining",
        "remaining_minutes": remaining / 60
    }


def check_all_tickets(tickets, now=None):
    """Check SLA status for a list of tickets."""
    results = []
    for t in tickets:
        sla = check_sla(t, now)
        sla["ticket_id"] = t.get("ticket_id", "")
        sla["priority"] = t.get("priority", "")
        results.append(sla)
    return results
