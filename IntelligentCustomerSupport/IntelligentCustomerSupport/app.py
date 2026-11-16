"""
Streamlit Dashboard - Intelligent Customer Support System with Escalation
"""

import streamlit as st
import pandas as pd
import json
import os
import csv
from datetime import datetime, timezone, timedelta

from classifier import classify_query
from resolver import load_knowledge_base, retrieve_article
from workflow_router import route_query
from ticket_manager import create_ticket, update_ticket_status, get_all_tickets, init_db, get_ticket
from notifications import generate_notification, approve_notification, send_with_retry, dispatch_notification, log_notification
from sla_monitor import check_sla, check_all_tickets
from human_review import apply_review_action, ALLOWED_ACTIONS, AUTHORIZED_REVIEWERS
from audit_logger import AuditLogger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "customer_queries.csv")
KB_PATH = os.path.join(BASE_DIR, "knowledge_base.json")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DB_PATH = os.path.join(BASE_DIR, "tickets.db")
AUDIT_PATH = os.path.join(BASE_DIR, "audit_log.csv")
NOTIF_LOG_PATH = os.path.join(BASE_DIR, "notification_log.csv")

st.set_page_config(page_title="Customer Support System", layout="wide")
st.title("Intelligent Customer Support System with Escalation")
st.caption("Lab 8 - SaaS Domain | VESIT")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_queries():
    df = pd.read_csv(CSV_PATH)
    return df


def validate_query(row):
    errors = []
    if not row.get("query_id", "").strip():
        errors.append("Missing query_id")
    if not row.get("customer_id", "").strip():
        errors.append("Missing customer_id")
    if not str(row.get("query_text", "")).strip():
        errors.append("Empty query_text")
    if not row.get("created_at", "").strip():
        errors.append("Missing created_at")
    return errors


tabs = st.tabs([
    "Architecture", "Data Ingestion", "Validation",
    "Classification", "Knowledge Base", "Workflow Routing",
    "Ticket Manager", "Human Review", "Notifications",
    "SLA Monitor", "Audit Log", "Full Pipeline",
    "Testing", "Evaluation"
])


# Tab 0: Architecture
with tabs[0]:
    st.header("System Architecture")
    st.markdown("""
    **Pipeline Flow:**

    1. **Data Ingestion** - Load customer queries from CSV
    2. **Validation** - Check required fields, reject invalid records
    3. **Classification** - Classify by intent, complexity, priority (keyword rules)
    4. **Knowledge Base Retrieval** - Search approved KB articles, compute match score
    5. **Workflow Routing** - Route to auto-resolve, human review, or escalation
    6. **Ticket Management** - Create tickets in SQLite, manage lifecycle
    7. **Human Review** - Authorized reviewers approve/edit/escalate/hold/resolve
    8. **Notifications** - Generate, approve, dispatch with retry logic
    9. **SLA Monitoring** - Track deadlines, flag at-risk and breached tickets
    10. **Audit Logging** - Append-only CSV log of all significant events
    """)
    st.subheader("Project Files")
    files = [
        ("classifier.py", "Rule-based query classifier"),
        ("resolver.py", "Knowledge base retrieval engine"),
        ("workflow_router.py", "Routing logic"),
        ("ticket_manager.py", "SQLite ticket lifecycle"),
        ("human_review.py", "Human review actions"),
        ("notifications.py", "Notification service with retries"),
        ("sla_monitor.py", "SLA deadline tracking"),
        ("audit_logger.py", "Append-only audit log"),
        ("app.py", "Streamlit dashboard"),
        ("test_support.py", "Test suite"),
        ("customer_queries.csv", "Sample input data"),
        ("knowledge_base.json", "Approved KB articles"),
        ("config.json", "SLA and system configuration"),
    ]
    st.table(pd.DataFrame(files, columns=["File", "Description"]))


# Tab 1: Data Ingestion
with tabs[1]:
    st.header("Step 1: Data Ingestion")
    st.markdown("Load customer queries from `customer_queries.csv`.")
    try:
        df = load_queries()
        st.success(f"Loaded {len(df)} queries")
        st.dataframe(df, use_container_width=True)
        st.subheader("Schema")
        st.json({col: str(dtype) for col, dtype in df.dtypes.items()})
    except Exception as e:
        st.error(f"Failed to load queries: {e}")


# Tab 2: Validation
with tabs[2]:
    st.header("Step 2: Query Validation")
    st.markdown("Each query is validated for required fields. Invalid records are rejected.")
    df = load_queries()
    valid_rows = []
    rejected_rows = []
    seen_ids = set()

    for _, row in df.iterrows():
        rec = row.to_dict()
        errs = validate_query(rec)
        qid = str(rec.get("query_id", ""))
        if qid in seen_ids:
            errs.append(f"Duplicate query_id: {qid}")
        if errs:
            rec["errors"] = "; ".join(errs)
            rejected_rows.append(rec)
        else:
            seen_ids.add(qid)
            valid_rows.append(rec)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Valid", len(valid_rows))
    with col2:
        st.metric("Rejected", len(rejected_rows))

    if rejected_rows:
        st.subheader("Rejected Records")
        st.dataframe(pd.DataFrame(rejected_rows), use_container_width=True)
    st.subheader("Valid Records")
    st.dataframe(pd.DataFrame(valid_rows), use_container_width=True)


# Tab 3: Classification
with tabs[3]:
    st.header("Step 3: Query Classification")
    st.markdown("Rule-based keyword matching classifies each query on three dimensions.")

    df = load_queries()
    results = []
    for _, row in df.iterrows():
        text = str(row.get("query_text", ""))
        cl = classify_query(text)
        results.append({
            "query_id": row["query_id"],
            "query_text": text[:80],
            "intent": cl["intent"],
            "complexity": cl["complexity"],
            "priority": cl["priority"],
        })
    rdf = pd.DataFrame(results)
    st.dataframe(rdf, use_container_width=True)

    st.subheader("Try Custom Query")
    custom = st.text_input("Enter a query to classify:", key="classify_input")
    if custom:
        r = classify_query(custom)
        st.json(r)


# Tab 4: Knowledge Base
with tabs[4]:
    st.header("Step 4: Knowledge Base Retrieval")
    kb = load_knowledge_base(KB_PATH)

    st.subheader("Approved Articles")
    approved = [a for a in kb if a.get("approved")]
    st.dataframe(pd.DataFrame(approved), use_container_width=True)

    unapproved = [a for a in kb if not a.get("approved")]
    if unapproved:
        st.subheader("Unapproved (excluded from retrieval)")
        st.dataframe(pd.DataFrame(unapproved), use_container_width=True)

    st.subheader("Test Retrieval")
    test_q = st.text_input("Query text:", key="kb_test")
    if test_q:
        article, score = retrieve_article(test_q, kb)
        if article:
            st.success(f"Match: {article['article_id']} (score: {score:.1f}%)")
            st.info(article["response"])
        else:
            st.warning("No matching article found")


# Tab 5: Workflow Routing
with tabs[5]:
    st.header("Step 5: Workflow Routing")
    st.markdown("""
    **Routing rules:**
    | Condition | Route |
    |---|---|
    | P1 priority | URGENT_HUMAN_ESCALATION |
    | High complexity | TECHNICAL_HUMAN_REVIEW |
    | No KB article found | CREATE_TICKET_AND_ESCALATE |
    | Score >= 70, Low complexity | PROPOSE_AUTO_RESOLUTION |
    | Score >= 40 | HUMAN_REVIEW |
    | Score < 40 | REQUEST_INFORMATION_OR_ESCALATE |
    """)

    df = load_queries()
    kb = load_knowledge_base(KB_PATH)
    route_results = []

    for _, row in df.iterrows():
        text = str(row.get("query_text", ""))
        if not text.strip():
            continue
        cl = classify_query(text)
        article, score = retrieve_article(text, kb)
        route = route_query(cl, score, article is not None)
        route_results.append({
            "query_id": row["query_id"],
            "intent": cl["intent"],
            "priority": cl["priority"],
            "match_score": f"{score:.1f}",
            "kb_article": article["article_id"] if article else "None",
            "route": route
        })

    st.dataframe(pd.DataFrame(route_results), use_container_width=True)


# Tab 6: Ticket Manager
with tabs[6]:
    st.header("Step 6: Ticket Management")
    st.markdown("Tickets are stored in SQLite with lifecycle transitions.")

    st.subheader("Lifecycle States")
    st.markdown("""
    OPEN -> TRIAGED -> ASSIGNED/IN_PROGRESS -> RESOLVED -> CLOSED

    Tickets can be reopened (RESOLVED -> IN_PROGRESS) if the issue persists.
    """)

    if st.button("View All Tickets", key="view_tickets"):
        tickets = get_all_tickets(DB_PATH)
        if tickets:
            st.dataframe(pd.DataFrame(tickets), use_container_width=True)
        else:
            st.info("No tickets yet. Run the Full Pipeline first.")

    st.subheader("Ticket Fields")
    fields = [
        ("ticket_id", "Unique ticket identifier"),
        ("query_id", "Links to incoming query"),
        ("customer_id", "Customer reference"),
        ("intent", "Classified intent"),
        ("priority", "P1-P4"),
        ("status", "Current lifecycle state"),
        ("assigned_team", "Support queue or agent"),
        ("first_response_due", "SLA first-response deadline"),
        ("resolution_due", "SLA resolution deadline"),
        ("resolution_summary", "Final resolution details"),
    ]
    st.table(pd.DataFrame(fields, columns=["Field", "Purpose"]))


# Tab 7: Human Review
with tabs[7]:
    st.header("Step 7: Human Review & Escalation")
    st.markdown(f"**Authorized reviewers:** {', '.join(sorted(AUTHORIZED_REVIEWERS))}")
    st.markdown(f"**Allowed actions:** {', '.join(sorted(ALLOWED_ACTIONS))}")

    st.subheader("Action Effects")
    action_effects = [
        ("APPROVE", "APPROVED_FOR_RESPONSE"),
        ("EDIT", "IN_REVIEW (or custom status)"),
        ("HOLD", "ON_HOLD"),
        ("REQUEST_INFORMATION", "AWAITING_CUSTOMER"),
        ("ESCALATE", "ESCALATED"),
        ("RESOLVE", "RESOLVED"),
    ]
    st.table(pd.DataFrame(action_effects, columns=["Action", "Resulting Status"]))

    st.subheader("Simulate Review")
    demo_ticket = {"ticket_id": "TKT-DEMO", "status": "IN_PROGRESS"}
    reviewer = st.selectbox("Reviewer:", sorted(AUTHORIZED_REVIEWERS) + ["Unauthorized_User"], key="hr_reviewer")
    action = st.selectbox("Action:", sorted(ALLOWED_ACTIONS), key="hr_action")
    if st.button("Apply Review", key="hr_apply"):
        try:
            result = apply_review_action(dict(demo_ticket), action, reviewer)
            st.success(f"Status changed to: {result['status']}")
            st.json(result)
        except (PermissionError, ValueError) as e:
            st.error(str(e))


# Tab 8: Notifications
with tabs[8]:
    st.header("Step 8: Notifications")
    st.markdown("""
    Notifications are generated as DRAFTs, require approval before dispatch,
    and use exponential backoff retry (up to 3 attempts).
    """)

    events_table = [
        ("Ticket created", "Customer", "Confirm receipt"),
        ("Ticket assigned", "Support agent", "Inform of assignment"),
        ("Ticket escalated", "Specialist team", "Communicate urgency"),
        ("Additional info requested", "Customer", "Explain required info"),
        ("Ticket resolved", "Customer", "Share resolution"),
        ("SLA at risk/breached", "Support lead", "Request intervention"),
    ]
    st.table(pd.DataFrame(events_table, columns=["Event", "Recipient", "Purpose"]))

    st.subheader("Simulate Notification")
    notif_ticket_id = st.text_input("Ticket ID:", "TKT-DEMO", key="notif_tid")
    notif_recipient = st.text_input("Customer ID:", "C101", key="notif_recip")
    notif_event = st.selectbox("Event:", ["CREATED", "ASSIGNED", "ESCALATED", "RESOLVED", "SLA_BREACH"], key="notif_event")
    auto_approve = st.checkbox("Auto-approve", value=True, key="notif_auto")

    if st.button("Send Notification", key="notif_send"):
        ticket = {"ticket_id": notif_ticket_id, "customer_id": notif_recipient}
        result = dispatch_notification(ticket, notif_event, auto_approve=auto_approve, log_path=NOTIF_LOG_PATH)
        if result["status"] == "SENT":
            st.success(f"Sent in {result['attempts']} attempt(s)")
        elif result["status"] == "NOT_SENT":
            st.warning("Not sent - notification not approved")
        else:
            st.error(f"Failed after {result['attempts']} attempts: {result.get('error', '')}")
        st.json(result)


# Tab 9: SLA Monitor
with tabs[9]:
    st.header("Step 9: SLA Monitoring")
    config = load_config()
    st.subheader("SLA Configuration")
    st.json(config["sla_minutes"])

    st.markdown("""
    **SLA States:**
    - **WITHIN_SLA** - Deadline not exceeded
    - **AT_RISK** - Approaching deadline (< 20% time remaining)
    - **BREACHED** - Deadline passed
    - **PAUSED** - SLA clock paused (ticket on hold)
    """)

    tickets = get_all_tickets(DB_PATH)
    if tickets:
        sla_results = check_all_tickets(tickets)
        sla_df = pd.DataFrame(sla_results)
        st.dataframe(sla_df, use_container_width=True)

        breached = [r for r in sla_results if r["sla_state"] == "BREACHED"]
        at_risk = [r for r in sla_results if r["sla_state"] == "AT_RISK"]
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Within SLA", len(sla_results) - len(breached) - len(at_risk))
        with col2:
            st.metric("At Risk", len(at_risk))
        with col3:
            st.metric("Breached", len(breached))
    else:
        st.info("No tickets yet. Run the Full Pipeline first.")


# Tab 10: Audit Log
with tabs[10]:
    st.header("Step 10: Audit Log")
    logger = AuditLogger(AUDIT_PATH)
    logs = logger.get_logs()
    if logs:
        st.dataframe(pd.DataFrame(logs), use_container_width=True)
        st.metric("Total Events", len(logs))
    else:
        st.info("No audit events yet. Run the Full Pipeline to generate entries.")


# Tab 11: Full Pipeline
with tabs[11]:
    st.header("Full Pipeline Execution")
    st.markdown("Run the complete workflow: ingest -> validate -> classify -> retrieve -> route -> ticket -> notify -> log")

    if st.button("Run Full Pipeline", key="run_pipeline"):
        config = load_config()
        sla = config["sla_minutes"]
        kb = load_knowledge_base(KB_PATH)
        logger = AuditLogger(AUDIT_PATH)
        df = load_queries()

        # Clean previous run
        for f in [DB_PATH, AUDIT_PATH, NOTIF_LOG_PATH]:
            if os.path.exists(f):
                os.remove(f)
        logger = AuditLogger(AUDIT_PATH)

        results = []
        valid_count = 0
        rejected_count = 0
        auto_resolved = 0
        escalated = 0
        seen_ids = set()

        progress = st.progress(0)
        status_text = st.empty()

        for i, (_, row) in enumerate(df.iterrows()):
            rec = row.to_dict()
            qid = str(rec.get("query_id", ""))
            progress.progress((i + 1) / len(df))
            status_text.text(f"Processing {qid}...")

            # Validate
            errs = validate_query(rec)
            if qid in seen_ids:
                errs.append("Duplicate query_id")
            if errs:
                rejected_count += 1
                logger.log("VALIDATION_REJECTED", query_id=qid,
                           error_details="; ".join(errs))
                results.append({
                    "query_id": qid, "status": "REJECTED",
                    "errors": "; ".join(errs),
                    "intent": "", "priority": "", "route": "",
                    "match_score": "", "ticket_id": ""
                })
                continue

            seen_ids.add(qid)
            valid_count += 1
            text = str(rec.get("query_text", ""))

            # Classify
            cl = classify_query(text)
            logger.log("CLASSIFICATION", query_id=qid,
                       intent=cl["intent"], complexity=cl["complexity"],
                       priority=cl["priority"])

            # Retrieve
            article, score = retrieve_article(text, kb)
            kb_id = article["article_id"] if article else ""
            logger.log("KB_RETRIEVAL", query_id=qid,
                       knowledge_article_id=kb_id,
                       match_score=f"{score:.1f}")

            # Route
            route = route_query(cl, score, article is not None)
            logger.log("ROUTING", query_id=qid, route=route)

            # Create ticket
            query_dict = {
                "query_id": qid,
                "customer_id": rec.get("customer_id", ""),
            }
            ticket = create_ticket(query_dict, cl, sla_minutes=sla, db_path=DB_PATH)
            tid = ticket["ticket_id"]

            # Apply route
            if route == "PROPOSE_AUTO_RESOLUTION":
                update_ticket_status(tid, "TRIAGED", db_path=DB_PATH)
                update_ticket_status(tid, "ASSIGNED", db_path=DB_PATH,
                                     assigned_team="Auto-Resolver")
                update_ticket_status(tid, "IN_PROGRESS", db_path=DB_PATH)
                ticket["status"] = "PENDING_APPROVAL"
                ticket["resolution_summary"] = article["response"] if article else ""
                auto_resolved += 1
                dispatch_notification(ticket, "CREATED", auto_approve=True,
                                      log_path=NOTIF_LOG_PATH)
            elif route in ("URGENT_HUMAN_ESCALATION", "TECHNICAL_HUMAN_REVIEW",
                           "CREATE_TICKET_AND_ESCALATE", "REQUEST_INFORMATION_OR_ESCALATE"):
                update_ticket_status(tid, "TRIAGED", db_path=DB_PATH)
                update_ticket_status(tid, "ESCALATED", db_path=DB_PATH,
                                     assigned_team="Support Team")
                escalated += 1
                dispatch_notification(ticket, "ESCALATED", auto_approve=True,
                                      log_path=NOTIF_LOG_PATH)
            else:  # HUMAN_REVIEW
                update_ticket_status(tid, "TRIAGED", db_path=DB_PATH)
                update_ticket_status(tid, "ASSIGNED", db_path=DB_PATH,
                                     assigned_team="Support Team")
                dispatch_notification(ticket, "ASSIGNED", auto_approve=True,
                                      log_path=NOTIF_LOG_PATH)

            logger.log("TICKET_CREATED", query_id=qid, ticket_id=tid,
                       ticket_status=ticket["status"], route=route)

            results.append({
                "query_id": qid, "status": "PROCESSED",
                "errors": "",
                "intent": cl["intent"],
                "priority": cl["priority"],
                "route": route,
                "match_score": f"{score:.1f}",
                "ticket_id": tid
            })

        progress.progress(1.0)
        status_text.text("Pipeline complete!")

        st.subheader("Summary")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Queries", len(df))
        with col2:
            st.metric("Valid", valid_count)
        with col3:
            st.metric("Rejected", rejected_count)
        with col4:
            st.metric("Escalated", escalated)

        st.subheader("Pipeline Results")
        st.dataframe(pd.DataFrame(results), use_container_width=True)

        st.subheader("Generated Tickets")
        tickets = get_all_tickets(DB_PATH)
        if tickets:
            st.dataframe(pd.DataFrame(tickets), use_container_width=True)

        st.subheader("Audit Log")
        logs = logger.get_logs()
        st.dataframe(pd.DataFrame(logs), use_container_width=True)


# Tab 12: Testing
with tabs[12]:
    st.header("Testing Procedure")
    st.markdown("Run `pytest test_support.py -v` from the project directory.")

    test_cases = [
        ("TC01", "Valid login query", "Classified as Login / Access"),
        ("TC02", "Billing and invoice query", "Routed to billing handling"),
        ("TC03", "Service-wide outage", "P1 priority, urgent escalation"),
        ("TC04", "Feature request", "Routed to product feedback queue"),
        ("TC05", "Empty query text", "Rejected during validation"),
        ("TC06", "Duplicate query ID", "Duplicate flagged or separate ticket"),
        ("TC07", "No matching knowledge article", "Ticket created for review"),
        ("TC08", "Match score above threshold, low-risk", "Proposed auto resolution"),
        ("TC09", "Match score below threshold", "Human review or escalation"),
        ("TC10", "High-risk query with high match score", "Escalation takes precedence"),
        ("TC11", "Notification succeeds on first attempt", "Status recorded as sent"),
        ("TC12", "Notification fails then succeeds", "Delivery recorded with retry count"),
        ("TC13", "All notification attempts fail", "Failure recorded for investigation"),
        ("TC14", "Ticket approaches SLA deadline", "At-risk alert generated"),
        ("TC15", "Ticket exceeds SLA deadline", "Breach recorded and alert generated"),
        ("TC16", "Reviewer edits a response", "Updated response and action recorded"),
        ("TC17", "Unauthorized approval attempt", "Action rejected, security event"),
        ("TC18", "Ticket reopened after failure", "Lifecycle state updated"),
        ("TC19", "Malformed knowledge-base JSON", "Controlled error, no unapproved response"),
        ("TC20", "No recipient for notification", "Dispatch fails gracefully"),
    ]
    st.table(pd.DataFrame(test_cases, columns=["Test ID", "Scenario", "Expected Result"]))


# Tab 13: Evaluation
with tabs[13]:
    st.header("Evaluation Metrics")

    tickets = get_all_tickets(DB_PATH)
    if not tickets:
        st.info("Run the Full Pipeline first to compute metrics.")
    else:
        total = len(tickets)
        df_queries = load_queries()
        total_queries = len(df_queries)

        # Validation success rate
        valid = total
        rejected = total_queries - total
        val_rate = valid / total_queries * 100 if total_queries else 0

        # KB resolution rate
        auto = len([t for t in tickets if t.get("resolution_summary")])
        kb_rate = auto / total * 100 if total else 0

        # Escalation rate
        esc = len([t for t in tickets if t.get("status") == "ESCALATED"])
        esc_rate = esc / total * 100 if total else 0

        # SLA compliance
        sla_results = check_all_tickets(tickets)
        breached = len([s for s in sla_results if s["sla_state"] == "BREACHED"])
        sla_rate = (total - breached) / total * 100 if total else 0

        # Notification success rate
        notif_path = NOTIF_LOG_PATH
        sent = 0
        notif_total = 0
        if os.path.exists(notif_path):
            with open(notif_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    notif_total += 1
                    if row.get("status") == "SENT":
                        sent += 1
        notif_rate = sent / notif_total * 100 if notif_total else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Validation Success Rate", f"{val_rate:.1f}%")
            st.metric("KB Resolution Rate", f"{kb_rate:.1f}%")
        with col2:
            st.metric("Escalation Rate", f"{esc_rate:.1f}%")
            st.metric("SLA Compliance Rate", f"{sla_rate:.1f}%")
        with col3:
            st.metric("Notification Success Rate", f"{notif_rate:.1f}%")
            st.metric("Total Tickets Created", total)

        st.subheader("Formulas")
        st.latex(r"Accuracy = \frac{Correct\ predictions}{Total\ predictions} \times 100")
        st.latex(r"Resolution\ Rate = \frac{Successfully\ resolved\ eligible\ queries}{Eligible\ queries\ processed} \times 100")
        st.latex(r"Escalation\ Rate = \frac{Queries\ escalated}{Total\ valid\ queries} \times 100")
        st.latex(r"SLA\ Compliance = \frac{Eligible\ tickets\ meeting\ SLA}{Eligible\ tickets\ with\ SLA} \times 100")
