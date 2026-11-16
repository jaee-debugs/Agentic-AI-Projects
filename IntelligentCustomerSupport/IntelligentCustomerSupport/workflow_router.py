"""
Workflow routing - decides how a query should be handled based on
classification, match score, and risk rules.
"""


def route_query(classification, match_score, article_found):
    """Route a query to the appropriate handling path.
    Returns one of:
      URGENT_HUMAN_ESCALATION, TECHNICAL_HUMAN_REVIEW,
      CREATE_TICKET_AND_ESCALATE, PROPOSE_AUTO_RESOLUTION,
      HUMAN_REVIEW, REQUEST_INFORMATION_OR_ESCALATE
    """
    priority = classification["priority"]
    complexity = classification["complexity"]

    if priority == "P1":
        return "URGENT_HUMAN_ESCALATION"

    if complexity == "High":
        return "TECHNICAL_HUMAN_REVIEW"

    if not article_found:
        return "CREATE_TICKET_AND_ESCALATE"

    if match_score >= 70 and complexity == "Low":
        return "PROPOSE_AUTO_RESOLUTION"

    if match_score >= 40:
        return "HUMAN_REVIEW"

    return "REQUEST_INFORMATION_OR_ESCALATE"
