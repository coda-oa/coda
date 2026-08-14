import re
from collections.abc import Sequence
from dataclasses import dataclass

from django.db.models import Q

type SearchFieldAliases = dict[str, str | list[str]]


@dataclass
class _PrefixedTerm:
    """A single recognised prefixed search term.

    Attributes:
        fields: The Django field lookups the term should be searched against.
        value:  The search value (quotes already stripped).
    """

    fields: list[str]
    value: str


@dataclass
class _PrefixedParseResult:
    """Result of extracting prefixed terms from a search string.

    Attributes:
        terms:     All recognised prefix:value terms found in the input.
        remaining: The input string with recognised prefixed terms removed,
                   ready for generic multi-field search.
    """

    terms: list[_PrefixedTerm]
    remaining: str


def build_search_filter(
    query: str,
    *fields: str,
    field_aliases: SearchFieldAliases | None = None,
) -> Q:
    """Build a Q filter that matches all words/phrases across any of the given fields.

    Each unquoted word or double-quoted phrase must appear (case-insensitively) in at
    least one of the fields - AND logic across words, OR across fields.

    When ``field_aliases`` is provided, terms prefixed with a recognised alias are
    scoped to the mapped field(s) instead of being searched across all ``*fields``.
    Prefixed terms use the same phrase/word splitting around the colon value:
    the value can be a double-quoted phrase (``author:"john doe"``) or a single word
    (``author:john``). Unprefixed terms remain in the generic multi-field search.

    Examples with fields=["title", "author__name"]:
        "mit press"               -> title ILIKE '%mit%' AND title ILIKE '%press%'
                                     OR  author ILIKE '%mit%' AND author ILIKE '%press%'
        '"mit press"'             -> title ILIKE '%mit press%' OR author ILIKE '%mit press%'
        '"mit press" john'        -> (phrase match) AND (word match)

    With field_aliases={"author": "author__name"}:
        'author:"john doe"'       -> author ILIKE '%john doe%'  (scoped to author)
        'author:"john doe" springer'
                                 -> (author ILIKE '%john doe%')
                                    AND (title ILIKE '%springer%' OR author ILIKE '%springer%')
    """
    if not query.strip():
        return Q()

    q = Q()

    result = _parse_prefixed_terms(query, field_aliases or {})

    for term in result.terms:
        if term.value.strip():
            q &= _match_any_field(term.value, term.fields)

    if result.remaining:
        phrases, words = _parse_search_terms(result.remaining)
        for value in [*phrases, *words]:
            if value.strip():
                q &= _match_any_field(value, fields)

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


def _parse_prefixed_terms(
    search_term: str,
    aliases: SearchFieldAliases,
) -> _PrefixedParseResult:
    """Extract field-prefixed terms (``prefix:value``) from the search string.

    Only prefixes present in ``aliases`` are extracted; unknown prefixes are left
    in the remaining string as-is.
    """
    # Normalise single-field aliases to lists for uniform handling
    normalized_aliases: dict[str, list[str]] = {
        k: [v] if isinstance(v, str) else v for k, v in aliases.items()
    }

    # Match either a quoted value ("...") or a single non-whitespace word
    pattern = re.compile(r"""(\w+):("(?:[^"]*)"|\S+)""")

    terms: list[_PrefixedTerm] = []

    def _replace(m: re.Match[str]) -> str:
        prefix = m.group(1)
        raw_value = m.group(2)
        if prefix in normalized_aliases:
            # Strip surrounding quotes if present
            value = raw_value.strip('"')
            if value:
                terms.append(_PrefixedTerm(fields=normalized_aliases[prefix], value=value))
            return ""
        return m.group(0)

    remaining = pattern.sub(_replace, search_term).strip()
    return _PrefixedParseResult(terms=terms, remaining=remaining)


def _match_any_field(value: str, fields: Sequence[str]) -> Q:
    """Build a Q that matches value (case-insensitively) in at least one of the fields.

    Returns:
        A Q joining one ``icontains`` lookup per field with OR logic.
    """
    q = Q()
    for field in fields:
        q |= Q(**{f"{field}__icontains": value})
    return q
