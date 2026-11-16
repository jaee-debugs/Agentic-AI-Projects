"""
Knowledge base retrieval and response scoring.
Searches approved KB articles by keyword match score.
"""

import json


def load_knowledge_base(path="knowledge_base.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def retrieve_article(query_text, knowledge_base):
    """Find the best matching approved KB article.
    Score = 100 * (matched_keywords / total_keywords).
    Returns (article, score) or (None, 0) if nothing matches."""
    if not query_text or not query_text.strip():
        return None, 0

    text = query_text.lower()
    matches = []

    for article in knowledge_base:
        if not article.get("approved", False):
            continue

        keywords = article.get("keywords", [])
        if not keywords:
            continue

        matched = [kw for kw in keywords if kw.lower() in text]
        if matched:
            score = len(matched) / len(keywords) * 100
            matches.append((score, article))

    if not matches:
        return None, 0

    score, article = max(matches, key=lambda x: x[0])
    return article, score
