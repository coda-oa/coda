import re
from collections.abc import Sequence
from dataclasses import dataclass

from django.db.models import Q


@dataclass(frozen=True)
class ScopedAlias:
    """A field alias with an additional row filter.

    Attributes:
        fields: The Django field lookups the term should be searched against.
        extra:  An additional Q condition applied to the same relation row as the
                field match, e.g. ``Q(publication__links__type__name="DOI")`` when
                ``fields`` is ``"publication__links__value"``. Must traverse the
                same relation path as ``fields`` so both conditions apply to one row.
    """

    fields: str | list[str]
    extra: Q


type SearchFieldAliases = dict[str, str | list[str] | ScopedAlias]

# Match a prefixed term: a word-char prefix, a colon, and either a
# double-quoted value ("...") or a single non-whitespace word
_PREFIXED_TERM_RE = re.compile(r"""\b(\w+):("[^"]*"|\S+)""")

# Match a double-quoted phrase, capturing its content
_QUOTED_PHRASE_RE = re.compile(r'"([^"]*)"')


@dataclass
class _PrefixedTerm:
    """A single recognised prefixed search term.

    Attributes:
        fields: The Django field lookups the term should be searched against.
        value:  The search value (quotes already stripped).
        extra:  Optional additional Q condition applied to the matched row.
    """

    fields: list[str]
    value: str
    extra: Q | None = None


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
    An alias may also be a ``ScopedAlias``, which ANDs an extra Q condition onto the
    matched row (e.g. only links of a given type).
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
            term_q = _match_any_field(term.value, term.fields)
            if term.extra is not None:
                term_q = term_q & term.extra
            q &= term_q

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
    phrases = _QUOTED_PHRASE_RE.findall(search_term)
    remaining = _QUOTED_PHRASE_RE.sub("", search_term).strip()
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
    # Normalise aliases to (fields, extra) pairs for uniform handling
    normalized_aliases: dict[str, tuple[list[str], Q | None]] = {
        k: _normalise_alias(v) for k, v in aliases.items()
    }

    terms: list[_PrefixedTerm] = []

    def _replace(m: re.Match[str]) -> str:
        prefix = m.group(1)
        raw_value = m.group(2)
        if prefix in normalized_aliases:
            # Strip surrounding quotes if present
            value = raw_value.strip('"')
            if value:
                fields, extra = normalized_aliases[prefix]
                terms.append(_PrefixedTerm(fields=fields, value=value, extra=extra))
            return ""
        return m.group(0)

    remaining = _PREFIXED_TERM_RE.sub(_replace, search_term).strip()
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


def _normalise_alias(alias: str | list[str] | ScopedAlias) -> tuple[list[str], Q | None]:
    """Normalise any alias form to a (fields, extra) pair.

    Returns:
        A tuple (fields, extra) where fields is a list of Django lookups and extra
        is the optional additional Q condition (None for plain field aliases).
    """
    if isinstance(alias, ScopedAlias):
        fields = [alias.fields] if isinstance(alias.fields, str) else alias.fields
        return fields, alias.extra
    fields = [alias] if isinstance(alias, str) else alias
    return fields, None


def alias_field_paths(aliases: SearchFieldAliases) -> list[str]:
    """All field paths referenced by an alias mapping, in dict order.

    Returns:
        The Django lookups referenced by every alias, flattened.
    """
    fields: list[str] = []
    for alias in aliases.values():
        normalised, _ = _normalise_alias(alias)
        fields.extend(normalised)
    return fields
