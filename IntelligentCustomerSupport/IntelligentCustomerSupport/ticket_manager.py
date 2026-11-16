"""
Ticket generation and lifecycle management using SQLite.
"""

import sqlite3
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4


DB_PATH = "tickets.db"

VALID_TRANSITIONS = {
    "OPEN": ["TRIAGED"],
    "TRIAGED": ["ASSIGNED", "ESCALATED"],
    "ASSIGNED": ["IN_PROGRESS", "ESCALATED"],
    "IN_PROGRESS": ["RESOLVED", "ESCALATED", "ON_HOLD", "AWAITING_CUSTOMER"],
    "ON_HOLD": ["IN_PROGRESS", "ESCALATED"],
    "AWAITING_CUSTOMER": ["IN_PROGRESS", "CLOSED"],
    "RESOLVED": ["CLOSED", "IN_PROGRESS"],
    "ESCALATED": ["ASSIGNED", "IN_PROGRESS", "RESOLVED"],
    "APPROVED_FOR_RESPONSE": ["RESOLVED", "CLOSED"],
    "IN_REVIEW": ["APPROVED_FOR_RESPONSE", "ESCALATED", "IN_PROGRESS"],
    "PENDING_APPROVAL": ["APPROVED_FOR_RESPONSE", "IN_REVIEW", "ESCALATED"],
    "CLOSED": [],
}


def init_db(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            query_id TEXT,
            customer_id TEXT,
            intent TEXT,
            complexity TEXT,
            priority TEXT,
            status TEXT,
            assigned_team TEXT,
            created_at TEXT,
            updated_at TEXT,
            first_response_due TEXT,
            resolution_due TEXT,
            resolution_summary TEXT
        )
    """)
    conn.commit()
    return conn


def create_ticket(query, classification, sla_minutes=None, db_path=None):
    """Create a new ticket from a query and its classification."""
    now = datetime.now(timezone.utc).isoformat()
    tid = "TKT-" + uuid4().hex[:8].upper()

    first_response_due = None
    resolution_due = None
    if sla_minutes:
        priority = classification["priority"]
        mins = sla_minutes.get(priority, 240)
        deadline = datetime.now(timezone.utc) + timedelta(minutes=mins)
        first_response_due = deadline.isoformat()
        resolution_due = (datetime.now(timezone.utc) + timedelta(minutes=mins * 2)).isoformat()

    ticket = {
        "ticket_id": tid,
        "query_id": query.get("query_id", ""),
        "customer_id": query.get("customer_id", ""),
        "intent": classification["intent"],
        "complexity": classification["complexity"],
        "priority": classification["priority"],
        "status": "OPEN",
        "assigned_team": None,
        "created_at": now,
        "updated_at": now,
        "first_response_due": first_response_due,
        "resolution_due": resolution_due,
        "resolution_summary": None,
    }

    conn = init_db(db_path)
    conn.execute("""
        INSERT INTO tickets VALUES (
            :ticket_id, :query_id, :customer_id, :intent, :complexity,
            :priority, :status, :assigned_team, :created_at, :updated_at,
            :first_response_due, :resolution_due, :resolution_summary
        )
    """, ticket)
    conn.commit()
    conn.close()
    return ticket


def update_ticket_status(ticket_id, new_status, db_path=None, resolution_summary=None, assigned_team=None):
    """Transition a ticket to a new status. Validates the transition."""
    conn = init_db(db_path)
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Ticket {ticket_id} not found")

    current = row["status"]
    allowed = VALID_TRANSITIONS.get(current, [])
    if new_status not in allowed:
        conn.close()
        raise ValueError(
            f"Invalid transition: {current} -> {new_status}. "
            f"Allowed: {allowed}"
        )

    now = datetime.now(timezone.utc).isoformat()
    updates = {"status": new_status, "updated_at": now, "ticket_id": ticket_id}

    sql = "UPDATE tickets SET status = :status, updated_at = :updated_at"
    if resolution_summary:
        sql += ", resolution_summary = :resolution_summary"
        updates["resolution_summary"] = resolution_summary
    if assigned_team:
        sql += ", assigned_team = :assigned_team"
        updates["assigned_team"] = assigned_team
    sql += " WHERE ticket_id = :ticket_id"

    conn.execute(sql, updates)
    conn.commit()

    updated = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    conn.close()
    return dict(updated)


def get_ticket(ticket_id, db_path=None):
    conn = init_db(db_path)
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_tickets(db_path=None):
    conn = init_db(db_path)
    rows = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_open_tickets(db_path=None):
    conn = init_db(db_path)
    rows = conn.execute(
        "SELECT * FROM tickets WHERE status NOT IN ('CLOSED', 'RESOLVED') ORDER BY created_at"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
