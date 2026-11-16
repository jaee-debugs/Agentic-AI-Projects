"""
Query classifier - rule-based keyword matching for intent, complexity, priority.
"""


RULES = [
    {
        "keywords": ["security incident", "data breach", "unauthorized access"],
        "intent": "Technical Error",
        "complexity": "High",
        "priority": "P1"
    },
    {
        "keywords": ["application is down", "service down", "outage", "down for all"],
        "intent": "Technical Error",
        "complexity": "High",
        "priority": "P1"
    },
    {
        "keywords": ["still unresolved", "did not work", "not resolved", "still not fixed"],
        "intent": "Unresolved Issue",
        "complexity": "High",
        "priority": "P1"
    },
    {
        "keywords": ["server error", "internal error", "export fails", "crash", "bug"],
        "intent": "Technical Error",
        "complexity": "Medium",
        "priority": "P2"
    },
    {
        "keywords": ["cannot log in", "account locked", "password reset", "login issue", "reset password"],
        "intent": "Login / Access",
        "complexity": "Medium",
        "priority": "P2"
    },
    {
        "keywords": ["invoice", "payment", "billing", "charge", "charged twice", "overcharged"],
        "intent": "Billing",
        "complexity": "Medium",
        "priority": "P2"
    },
    {
        "keywords": ["dark mode", "feature request", "add feature", "new feature", "can you add"],
        "intent": "Feature Request",
        "complexity": "Low",
        "priority": "P4"
    },
    {
        "keywords": ["subscription", "plan", "pricing", "features included", "basic plan", "change plan"],
        "intent": "General Information",
        "complexity": "Low",
        "priority": "P3"
    },
]

DEFAULT_CLASSIFICATION = {
    "intent": "General Information",
    "complexity": "Low",
    "priority": "P3"
}


def classify_query(query_text):
    """Classify a query by intent, complexity, and priority using keyword rules.
    Rules are checked in order; first match wins. Critical/security rules come first."""
    if not query_text or not query_text.strip():
        return {
            "intent": "General Information",
            "complexity": "Low",
            "priority": "P3",
            "matched_rule": None
        }

    text = query_text.lower()

    for i, rule in enumerate(RULES):
        for kw in rule["keywords"]:
            if kw.lower() in text:
                return {
                    "intent": rule["intent"],
                    "complexity": rule["complexity"],
                    "priority": rule["priority"],
                    "matched_rule": i
                }

    return {
        "intent": DEFAULT_CLASSIFICATION["intent"],
        "complexity": DEFAULT_CLASSIFICATION["complexity"],
        "priority": DEFAULT_CLASSIFICATION["priority"],
        "matched_rule": None
    }
