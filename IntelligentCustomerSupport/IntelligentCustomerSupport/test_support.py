"""
Test suite for Intelligent Customer Support System.
Covers: classification, KB retrieval, routing, tickets, notifications,
        SLA monitoring, human review, audit logging.
"""

import os
import json
import pytest
from datetime import datetime, timezone, timedelta

from classifier import classify_query
from resolver import load_knowledge_base, retrieve_article
from workflow_router import route_query
from ticket_manager import create_ticket, update_ticket_status, get_ticket, init_db
from notifications import (
    generate_notification, approve_notification,
    send_with_retry, dispatch_notification
)
from sla_monitor import check_sla
from human_review import apply_review_action, ALLOWED_ACTIONS, AUTHORIZED_REVIEWERS
from audit_logger import AuditLogger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_PATH = os.path.join(BASE_DIR, "knowledge_base.json")
TEST_DB = os.path.join(BASE_DIR, "test_tickets.db")
TEST_AUDIT = os.path.join(BASE_DIR, "test_audit.csv")
TEST_NOTIF_LOG = os.path.join(BASE_DIR, "test_notif.csv")


@pytest.fixture(autouse=True)
def cleanup():
    yield
    for f in [TEST_DB, TEST_AUDIT, TEST_NOTIF_LOG]:
        if os.path.exists(f):
            os.remove(f)


@pytest.fixture
def kb():
    return load_knowledge_base(KB_PATH)


# TC01: Valid login query
class TestClassification:
    def test_login_query(self):
        r = classify_query("I cannot log in to my account")
        assert r["intent"] == "Login / Access"
        assert r["priority"] == "P2"

    # TC02: Billing query
    def test_billing_query(self):
        r = classify_query("My invoice shows an unauthorized charge")
        assert r["intent"] == "Billing"

    # TC03: Service-wide outage -> P1
    def test_outage_p1(self):
        r = classify_query("The application is down for all our users")
        assert r["priority"] == "P1"
        assert r["complexity"] == "High"

    # TC04: Feature request
    def test_feature_request(self):
        r = classify_query("Can you add dark mode to the dashboard?")
        assert r["intent"] == "Feature Request"
        assert r["priority"] == "P4"

    # TC05: Empty query
    def test_empty_query(self):
        r = classify_query("")
        assert r["intent"] == "General Information"
        assert r["priority"] == "P3"

    # TC10: High-risk with security incident
    def test_security_incident_p1(self):
        r = classify_query("We detected a security incident on our account")
        assert r["priority"] == "P1"

    def test_unresolved_issue(self):
        r = classify_query("The problem is still unresolved after three contacts")
        assert r["intent"] == "Unresolved Issue"
        assert r["priority"] == "P1"

    def test_general_info_default(self):
        r = classify_query("Hello, I have a question about something random")
        assert r["intent"] == "General Information"


# TC07, TC08, TC09: Knowledge base retrieval
class TestResolver:
    def test_matching_article(self, kb):
        article, score = retrieve_article("I cannot log in and my password reset failed", kb)
        assert article is not None
        assert article["article_id"] == "KB001"
        assert score > 0

    def test_no_match(self, kb):
        article, score = retrieve_article("something completely unrelated xyz abc", kb)
        assert article is None
        assert score == 0

    def test_unapproved_article_excluded(self, kb):
        # KB007 has keywords for 2fa but is not approved
        article, score = retrieve_article("two-factor authentication help", kb)
        assert article is None or article.get("approved", False) is True

    def test_high_score_billing(self, kb):
        article, score = retrieve_article("invoice payment billing charge", kb)
        assert article is not None
        assert score >= 70

    def test_empty_query(self, kb):
        article, score = retrieve_article("", kb)
        assert article is None


class TestRouting:
    def test_p1_always_escalates(self):
        cl = {"priority": "P1", "complexity": "High"}
        assert route_query(cl, 90, True) == "URGENT_HUMAN_ESCALATION"

    def test_high_complexity_review(self):
        cl = {"priority": "P2", "complexity": "High"}
        assert route_query(cl, 80, True) == "TECHNICAL_HUMAN_REVIEW"

    def test_no_article_escalate(self):
        cl = {"priority": "P3", "complexity": "Low"}
        assert route_query(cl, 0, False) == "CREATE_TICKET_AND_ESCALATE"

    # TC08: High score + low complexity -> auto resolve
    def test_auto_resolve(self):
        cl = {"priority": "P3", "complexity": "Low"}
        assert route_query(cl, 75, True) == "PROPOSE_AUTO_RESOLUTION"

    # TC09: Medium score -> human review
    def test_human_review(self):
        cl = {"priority": "P3", "complexity": "Medium"}
        assert route_query(cl, 55, True) == "HUMAN_REVIEW"

    def test_low_score_escalate(self):
        cl = {"priority": "P3", "complexity": "Medium"}
        assert route_query(cl, 30, True) == "REQUEST_INFORMATION_OR_ESCALATE"


class TestTicketManager:
    def test_create_ticket(self):
        q = {"query_id": "Q001", "customer_id": "C101"}
        cl = {"intent": "Billing", "complexity": "Medium", "priority": "P2"}
        t = create_ticket(q, cl, db_path=TEST_DB)
        assert t["ticket_id"].startswith("TKT-")
        assert t["status"] == "OPEN"

    # TC06: Duplicate query ID still gets unique ticket
    def test_unique_ticket_ids(self):
        q = {"query_id": "Q001", "customer_id": "C101"}
        cl = {"intent": "Billing", "complexity": "Medium", "priority": "P2"}
        t1 = create_ticket(q, cl, db_path=TEST_DB)
        t2 = create_ticket(q, cl, db_path=TEST_DB)
        assert t1["ticket_id"] != t2["ticket_id"]

    def test_valid_transition(self):
        q = {"query_id": "Q002", "customer_id": "C102"}
        cl = {"intent": "Technical Error", "complexity": "High", "priority": "P1"}
        t = create_ticket(q, cl, db_path=TEST_DB)
        updated = update_ticket_status(t["ticket_id"], "TRIAGED", db_path=TEST_DB)
        assert updated["status"] == "TRIAGED"

    def test_invalid_transition(self):
        q = {"query_id": "Q003", "customer_id": "C103"}
        cl = {"intent": "Billing", "complexity": "Low", "priority": "P3"}
        t = create_ticket(q, cl, db_path=TEST_DB)
        with pytest.raises(ValueError, match="Invalid transition"):
            update_ticket_status(t["ticket_id"], "CLOSED", db_path=TEST_DB)

    # TC18: Ticket reopened
    def test_reopen_resolved_ticket(self):
        q = {"query_id": "Q004", "customer_id": "C104"}
        cl = {"intent": "Login / Access", "complexity": "Medium", "priority": "P2"}
        t = create_ticket(q, cl, db_path=TEST_DB)
        update_ticket_status(t["ticket_id"], "TRIAGED", db_path=TEST_DB)
        update_ticket_status(t["ticket_id"], "ASSIGNED", db_path=TEST_DB)
        update_ticket_status(t["ticket_id"], "IN_PROGRESS", db_path=TEST_DB)
        update_ticket_status(t["ticket_id"], "RESOLVED", db_path=TEST_DB)
        reopened = update_ticket_status(t["ticket_id"], "IN_PROGRESS", db_path=TEST_DB)
        assert reopened["status"] == "IN_PROGRESS"

    def test_sla_deadline_set(self):
        q = {"query_id": "Q005", "customer_id": "C105"}
        cl = {"intent": "Billing", "complexity": "Medium", "priority": "P2"}
        sla = {"P1": 15, "P2": 60, "P3": 240, "P4": 1440}
        t = create_ticket(q, cl, sla_minutes=sla, db_path=TEST_DB)
        assert t["first_response_due"] is not None


# TC11, TC12, TC13
class TestNotifications:
    def test_draft_status(self):
        ticket = {"ticket_id": "TKT-TEST01", "customer_id": "C101"}
        n = generate_notification(ticket, "CREATED")
        assert n["status"] == "DRAFT"

    def test_approve_and_send(self):
        ticket = {"ticket_id": "TKT-TEST02", "customer_id": "C102"}
        n = generate_notification(ticket, "ASSIGNED")
        approve_notification(n, "Manager")
        result = send_with_retry(n)
        assert result["status"] == "SENT"
        assert result["attempts"] == 1

    def test_unapproved_not_sent(self):
        ticket = {"ticket_id": "TKT-TEST03", "customer_id": "C103"}
        n = generate_notification(ticket, "CREATED")
        result = send_with_retry(n)
        assert result["status"] == "NOT_SENT"

    # TC13: All attempts fail
    def test_all_retries_fail(self):
        ticket = {"ticket_id": "TKT-TEST04", "customer_id": "FAIL_TEST"}
        n = generate_notification(ticket, "ESCALATED")
        approve_notification(n, "Admin")
        result = send_with_retry(n, max_attempts=3)
        assert result["status"] == "FAILED"
        assert result["attempts"] == 3

    # TC12: Retry succeeds on later attempt (simulated via dispatch)
    def test_dispatch_auto_approve(self):
        ticket = {"ticket_id": "TKT-TEST05", "customer_id": "C105"}
        result = dispatch_notification(ticket, "RESOLVED", auto_approve=True, log_path=TEST_NOTIF_LOG)
        assert result["status"] == "SENT"

    # TC20: No recipient
    def test_no_recipient_fails(self):
        ticket = {"ticket_id": "TKT-TEST06", "customer_id": ""}
        n = generate_notification(ticket, "CREATED")
        approve_notification(n, "Admin")
        result = send_with_retry(n)
        assert result["status"] == "FAILED"


class TestSLAMonitor:
    # TC14: At risk
    def test_at_risk(self):
        now = datetime.now(timezone.utc)
        ticket = {
            "ticket_id": "TKT-SLA01",
            "status": "OPEN",
            "priority": "P2",
            "created_at": (now - timedelta(minutes=55)).isoformat(),
            "first_response_due": (now + timedelta(minutes=5)).isoformat(),
        }
        result = check_sla(ticket, now)
        assert result["sla_state"] == "AT_RISK"

    # TC15: Breached
    def test_breached(self):
        now = datetime.now(timezone.utc)
        ticket = {
            "ticket_id": "TKT-SLA02",
            "status": "OPEN",
            "priority": "P1",
            "created_at": (now - timedelta(minutes=30)).isoformat(),
            "first_response_due": (now - timedelta(minutes=5)).isoformat(),
        }
        result = check_sla(ticket, now)
        assert result["sla_state"] == "BREACHED"

    def test_within_sla(self):
        now = datetime.now(timezone.utc)
        ticket = {
            "ticket_id": "TKT-SLA03",
            "status": "OPEN",
            "priority": "P3",
            "created_at": now.isoformat(),
            "first_response_due": (now + timedelta(minutes=200)).isoformat(),
        }
        result = check_sla(ticket, now)
        assert result["sla_state"] == "WITHIN_SLA"

    def test_paused_on_hold(self):
        ticket = {
            "ticket_id": "TKT-SLA04",
            "status": "ON_HOLD",
            "priority": "P2",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "first_response_due": datetime.now(timezone.utc).isoformat(),
        }
        result = check_sla(ticket)
        assert result["sla_state"] == "PAUSED"

    def test_resolved_within_sla(self):
        ticket = {
            "ticket_id": "TKT-SLA05",
            "status": "RESOLVED",
            "priority": "P1",
        }
        result = check_sla(ticket)
        assert result["sla_state"] == "WITHIN_SLA"


# TC16, TC17
class TestHumanReview:
    def test_approve_action(self):
        ticket = {"ticket_id": "TKT-HR01", "status": "IN_REVIEW"}
        result = apply_review_action(ticket, "APPROVE", "Support_Lead")
        assert result["status"] == "APPROVED_FOR_RESPONSE"
        assert result["last_reviewer"] == "Support_Lead"

    def test_edit_action(self):
        ticket = {"ticket_id": "TKT-HR02", "status": "IN_REVIEW"}
        result = apply_review_action(
            ticket, "EDIT", "Senior_Agent",
            edit_response="Updated response", new_status="APPROVED_FOR_RESPONSE"
        )
        assert result["status"] == "APPROVED_FOR_RESPONSE"
        assert result["resolution_summary"] == "Updated response"

    def test_hold_action(self):
        ticket = {"ticket_id": "TKT-HR03", "status": "IN_PROGRESS"}
        result = apply_review_action(ticket, "HOLD", "Manager")
        assert result["status"] == "ON_HOLD"

    def test_escalate_action(self):
        ticket = {"ticket_id": "TKT-HR04", "status": "IN_PROGRESS"}
        result = apply_review_action(ticket, "ESCALATE", "Admin")
        assert result["status"] == "ESCALATED"

    # TC17: Unauthorized reviewer
    def test_unauthorized_reviewer(self):
        ticket = {"ticket_id": "TKT-HR05", "status": "IN_REVIEW"}
        with pytest.raises(PermissionError):
            apply_review_action(ticket, "APPROVE", "Random_User")

    def test_invalid_action(self):
        ticket = {"ticket_id": "TKT-HR06", "status": "IN_REVIEW"}
        with pytest.raises(ValueError):
            apply_review_action(ticket, "DELETE", "Admin")

    def test_resolve_with_summary(self):
        ticket = {"ticket_id": "TKT-HR07", "status": "IN_PROGRESS"}
        result = apply_review_action(ticket, "RESOLVE", "Manager", edit_response="Issue fixed")
        assert result["status"] == "RESOLVED"
        assert result["resolution_summary"] == "Issue fixed"


class TestAuditLogger:
    def test_log_creation(self):
        logger = AuditLogger(TEST_AUDIT)
        logger.log("CLASSIFICATION", query_id="Q001", ticket_id="TKT-001")
        logs = logger.get_logs()
        assert len(logs) == 1
        assert logs[0]["query_id"] == "Q001"

    def test_append_only(self):
        logger = AuditLogger(TEST_AUDIT)
        logger.log("CLASSIFICATION", query_id="Q001")
        logger.log("ROUTING", query_id="Q002")
        logger.log("NOTIFICATION", query_id="Q003")
        logs = logger.get_logs()
        assert len(logs) == 3

    def test_timestamp_present(self):
        logger = AuditLogger(TEST_AUDIT)
        logger.log("TEST_EVENT", query_id="Q001")
        logs = logger.get_logs()
        assert logs[0]["timestamp"] != ""

    def test_filter_by_ticket(self):
        logger = AuditLogger(TEST_AUDIT)
        logger.log("CLASSIFICATION", query_id="Q001", ticket_id="TKT-A")
        logger.log("ROUTING", query_id="Q002", ticket_id="TKT-B")
        logger.log("NOTIFICATION", query_id="Q001", ticket_id="TKT-A")
        filtered = logger.get_logs_for_ticket("TKT-A")
        assert len(filtered) == 2

    # TC19: Malformed KB
    def test_malformed_kb_handling(self):
        # Attempting to load a non-existent KB should raise
        with pytest.raises(FileNotFoundError):
            load_knowledge_base("nonexistent_kb.json")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
