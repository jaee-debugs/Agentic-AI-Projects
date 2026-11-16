"""
Human review and escalation module.
Allows authorized reviewers to take actions on tickets.
"""


ALLOWED_ACTIONS = {
    "APPROVE", "EDIT", "HOLD",
    "REQUEST_INFORMATION", "ESCALATE", "RESOLVE"
}

AUTHORIZED_REVIEWERS = {
    "Support_Lead", "Senior_Agent", "Manager", "Admin"
}

ACTION_STATUS_MAP = {
    "APPROVE": "APPROVED_FOR_RESPONSE",
    "EDIT": "IN_REVIEW",
    "HOLD": "ON_HOLD",
    "REQUEST_INFORMATION": "AWAITING_CUSTOMER",
    "ESCALATE": "ESCALATED",
    "RESOLVE": "RESOLVED",
}


def apply_review_action(ticket, action, reviewer_id, edit_response=None, new_status=None):
    """Apply a human review action to a ticket.
    Validates the reviewer and action before applying."""
    if reviewer_id not in AUTHORIZED_REVIEWERS:
        raise PermissionError(
            f"Reviewer '{reviewer_id}' is not authorized. "
            f"Allowed: {sorted(AUTHORIZED_REVIEWERS)}"
        )

    if action not in ALLOWED_ACTIONS:
        raise ValueError(
            f"Invalid action '{action}'. Allowed: {sorted(ALLOWED_ACTIONS)}"
        )

    ticket["last_reviewer"] = reviewer_id
    ticket["review_action"] = action

    if action == "EDIT" and new_status:
        ticket["status"] = new_status
        if edit_response:
            ticket["resolution_summary"] = edit_response
    else:
        ticket["status"] = ACTION_STATUS_MAP[action]

    if action == "RESOLVE" and edit_response:
        ticket["resolution_summary"] = edit_response

    return ticket
