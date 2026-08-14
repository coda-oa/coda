import re

from django.db.models import Q


def build_search_filter(query: str, *fields: str) -> Q:
    """Build a Q filter that matches all words/phrases across any of the given fields.

    Each unquoted word or double-quoted phrase^ must appear (case-insensitively) in at
    least one of the fields — AND logic across words, OR across fields.

    Examples with fields=["title", "author__name"]:
        "mit press"        -> title ILIKE '%mit%' AND title ILIKE '%press%'
                              OR  author ILIKE '%mit%' AND author ILIKE '%press%'
        '"mit press"'      -> title ILIKE '%mit press%' OR author ILIKE '%mit press%'
        '"mit press" springer'
                           -> (phrase match) AND (word match)
    """
    if not query.strip():
        return Q()

    phrases, words = _parse_search_terms(query)
    q = Q()

    for phrase in phrases:
        if not phrase.strip():
            continue
        phrase_q = Q()
        for field in fields:
            phrase_q |= Q(**{f"{field}__icontains": phrase})
        q &= phrase_q

    for word in words:
        word_q = Q()
        for field in fields:
            word_q |= Q(**{f"{field}__icontains": word})
        q &= word_q

    return q


def _parse_search_terms(search_term: str) -> tuple[list[str], list[str]]:
    """Split a search string into double-quoted phrases and remaining unquoted words.

    Returns:
        A tuple (phrases, words) where:
        - phrases: content inside matched double-quote pairs
        - words:   tokens remaining after removing quoted portions, split on whitespace

    Unmatched quotes are left in the word tokens as literal characters.
    """
    phrases = re.findall(r'"([^"]*)"', search_term)
    remaining = re.sub(r'"[^"]*"', "", search_term).strip()
    words = remaining.split() if remaining else []
    return phrases, words
