import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from django.db.models import Q


@dataclass(frozen=True)
class ScopedAlias:
    """A field alias with an additional row filter and optional value normalisation.

    Attributes:
        fields:    The Django field lookup the term should be searched against.
        extra:     An additional Q condition applied to the same relation row as the
                   field match, e.g. ``Q(publication__links__type__name="DOI")`` when
                   ``fields`` is ``"publication__links__value"``. Must traverse the
                   same relation path as ``fields`` so both conditions apply to one row.
        normalize: Optional callable applied to the user's value before matching, so
                   alternative spellings of an identifier (e.g. resolver URLs) match
                   the form stored in the database.
        detect:    Optional callable that recognises an unprefixed identifier value
                   and returns its canonical form (or None). Recognised unquoted
                   words are scoped to this alias instead of searched generically.
    """

    fields: str
    extra: Q
    normalize: Callable[[str], str] | None = None
    detect: Callable[[str], str | None] | None = None


type SearchFieldAliases = dict[str, str | list[str] | ScopedAlias]

type _AliasSpec = tuple[
    list[str],
    Q,
    Callable[[str], str] | None,
    Callable[[str], str | None] | None,
]

# Match a prefixed term: a word-char prefix, a colon, and either a
# double-quoted value ("...") or a single non-whitespace word
_PREFIXED_TERM_RE = re.compile(r"""\b(\w+):("[^"]*"|\S+)""")

# Match a double-quoted phrase, capturing its content
_QUOTED_PHRASE_RE = re.compile(r'"([^"]*)"')

# Standalone conjunction words carry no search weight and are dropped from
# unquoted word search. Quoted phrases and prefix values are unaffected.
_STOP_WORDS = {"and", "&"}


@dataclass
class _PrefixedTerm:
    """A single recognised prefixed search term.

    Attributes:
        fields: The Django field lookups the term should be searched against.
        value:  The search value (quotes already stripped).
        extra:  Additional Q condition applied to the matched row; an empty Q
                means no scope.
    """

    fields: list[str]
    value: str
    extra: Q = field(default_factory=Q)


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

    When ``*fields`` is omitted and ``field_aliases`` is given, the generic fields
    default to all field paths referenced by the aliases; when ``*fields`` is given
    explicitly it replaces the derived list.

    Each unquoted word or double-quoted phrase must appear (case-insensitively) in at
    least one of the fields - AND logic across words, OR across fields.

    When ``field_aliases`` is provided, terms prefixed with a recognised alias are
    scoped to the mapped field(s) instead of being searched across all ``*fields``.
    An alias may also be a ``ScopedAlias``, which ANDs an extra Q condition onto the
    matched row (e.g. only links of a given type).
    A ``ScopedAlias`` may declare a ``detect`` callable: an unquoted generic word it
    recognises as that identifier (e.g. a bare DOI or EISSN) is then scoped to the
    alias as if the prefix had been typed. Detector matches use the alias order, so
    the first accepting detector claims the word. Quoted phrases are never detected.
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

    if fields:
        generic_fields = list(fields)
    else:
        generic_fields = alias_field_paths(field_aliases or {})

    q = Q()

    result = _parse_prefixed_terms(query, field_aliases or {})

    for term in result.terms:
        q &= _match_any_field(term.value, term.fields) & term.extra

    if result.remaining:
        phrases, words = _parse_search_terms(result.remaining)
        words = [word for word in words if word.lower() not in _STOP_WORDS]
        phrases = [phrase for phrase in phrases if phrase.strip()]
        detected, words = _detect_identifiers(words, field_aliases or {})
        for term in detected:
            q &= _match_any_field(term.value, term.fields) & term.extra
        for value in [*phrases, *words]:
            q &= _match_any_field(value, generic_fields)

    if not q.children and query.strip():
        # The query consisted only of stop words (or stop-word-only phrases):
        # without this fallback it would match every row. Search it literally.
        q = _match_any_field(query, generic_fields)

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
    # Normalise aliases to (fields, extra, normalize, detect) tuples for uniform handling
    normalized_aliases: dict[str, _AliasSpec] = {k: _normalise_alias(v) for k, v in aliases.items()}

    terms: list[_PrefixedTerm] = []

    def _replace(m: re.Match[str]) -> str:
        prefix = m.group(1)
        raw_value = m.group(2)
        if prefix in normalized_aliases:
            # Strip surrounding quotes if present
            value = raw_value.strip('"')
            fields, extra, normalize, _ = normalized_aliases[prefix]
            # Whitespace-only values carry no term; normalizers may reject them
            if normalize is not None and value.strip():
                value = normalize(value)
            if value.strip():
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
    for f in fields:
        q |= Q(**{f"{f}__icontains": value})
    return q


def _identifier_term(word: str, specs: Sequence[_AliasSpec]) -> _PrefixedTerm | None:
    """First scoped identifier term whose detector claims ``word``, if any."""
    for fields, extra, _, detect in specs:
        if detect is None:
            continue
        value = detect(word)
        if value is not None:
            return _PrefixedTerm(fields=fields, value=value, extra=extra)
    return None


def _detect_identifiers(
    words: Sequence[str], aliases: SearchFieldAliases
) -> tuple[list[_PrefixedTerm], list[str]]:
    """Route identifier-shaped words through the aliases' detectors.

    The first alias (in mapping order) whose detector accepts a word claims it.

    Returns:
        A tuple (detected, remaining) where detected holds scoped identifier terms
        and remaining holds words that no detector recognised.
    """
    specs = [_normalise_alias(alias) for alias in aliases.values()]
    matches = [(word, _identifier_term(word, specs)) for word in words]
    return (
        [term for _, term in matches if term is not None],
        [word for word, term in matches if term is None],
    )


def _normalise_alias(alias: str | list[str] | ScopedAlias) -> _AliasSpec:
    """Normalise any alias form to a (fields, extra, normalize, detect) tuple.

    Returns:
        A tuple (fields, extra, normalize, detect) where fields is a list of Django
        lookups, extra is the additional Q condition (an empty Q for plain field
        aliases), normalize is the optional value normaliser and detect the optional
        unprefixed-identifier recogniser from a ``ScopedAlias``.
    """
    if isinstance(alias, ScopedAlias):
        return [alias.fields], alias.extra, alias.normalize, alias.detect
    fields = [alias] if isinstance(alias, str) else alias
    return fields, Q(), None, None


def alias_field_paths(aliases: SearchFieldAliases) -> list[str]:
    """All field paths referenced by an alias mapping, in dict order, de-duplicated.

    Returns:
        The Django lookups referenced by every alias, flattened; a path shared by
        several aliases (e.g. contract link values scoped per link type) appears once.
    """
    paths = [path for alias in aliases.values() for path in _normalise_alias(alias)[0]]
    return list(dict.fromkeys(paths))
