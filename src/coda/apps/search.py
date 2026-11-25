import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from django.db.models import Q


@dataclass(frozen=True)
class ScopedAlias:
    """Declaration of a prefixed search alias in a ``SearchFieldAliases`` mapping.

    A ``ScopedAlias`` is configuration; it carries no search value. The filter
    builder normalises it to an internal ``_NormalizedAlias`` and, when the query
    contains a matching prefix, creates one ``_PrefixedTerm`` per occurrence.

    Attributes:
        fields:    The Django field lookup used for prefix matching and included in
                   generic multi-field search. For prefix matching the term searches
                   this field, optionally narrowed by ``extra``.
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
        term_query: Optional callable that builds the Q condition for one term from
                   its normalised value. When set, it replaces the field/extra match
                   for prefixed and detected terms; ``fields`` still participates in
                   generic search. Use it for aliases whose field traverses a to-many
                   relation, so repeated terms can each match a different related row.

    Examples:
        A prefix scoped to DOI links::

            aliases = {
                "doi": ScopedAlias(
                    "publication__links__value",
                    Q(publication__links__type__name="DOI"),
                ),
            }
            # doi:10.1234/abc -> link value match AND link type DOI

        A per-term query, so each author term may match a different author row::

            aliases = {
                "author": ScopedAlias(
                    "publication__relevant_authors__name",
                    Q(),
                    term_query=_author_matches,
                ),
            }
            # author:"Jane Doe" author:"John Roe" -> two independent EXISTS
            # (_author_matches is defined in fundingrequest_query.py)
    """

    fields: str
    extra: Q
    normalize: Callable[[str], str] | None = None
    detect: Callable[[str], str | None] | None = None
    term_query: Callable[[str], Q] | None = None


@dataclass(frozen=True)
class _NormalizedAlias:
    """Internal, value-free form of any ``SearchFieldAliases`` entry.

    ``_normalise_alias`` converts every accepted declaration form to this type, so
    parsing code has one shape to handle. ``fields`` is always a list because a
    plain alias may name several fields; a ``ScopedAlias``'s ``extra``, ``normalize``,
    ``detect`` and ``term_query`` are copied. This type carries no search value;
    ``_PrefixedTerm`` adds the value for one matched term.

    Examples::

        "title"                    -> _NormalizedAlias(fields=["title"])
        ["title", "author__name"]  -> _NormalizedAlias(fields=["title", "author__name"])
        ScopedAlias("links__value", Q(links__type__name="DOI"))
            -> _NormalizedAlias(
                   fields=["links__value"],
                   extra=Q(links__type__name="DOI"),
               )
    """

    fields: list[str]
    extra: Q = field(default_factory=Q)
    normalize: Callable[[str], str] | None = None
    detect: Callable[[str], str | None] | None = None
    term_query: Callable[[str], Q] | None = None


# Public alias declaration forms accepted by build_search_filter:
#   "title"                         -> one field for prefix and generic search
#   ["title", "author__name"]       -> several fields for prefix and generic search
#   ScopedAlias(fields, extra, ...) -> scoped prefix with optional hooks
type SearchFieldAliases = dict[str, str | list[str] | ScopedAlias]

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
    """One concrete term parsed from a search query.

    Unlike ``ScopedAlias`` (declaration) and ``_NormalizedAlias`` (normalised
    declaration), this carries the actual search value. A configured prefix or a
    detected bare identifier creates one, and ``_term_query`` turns it into the Q
    condition.

    Attributes:
        fields: The Django field lookups the term should be searched against.
        value:  The search value (quotes already stripped).
        extra:  Additional Q condition applied to the matched row; an empty Q
                means no scope.
        term_query: Optional callable that builds the term's Q condition from value.

    Examples::

        title:"john doe"
            -> _PrefixedTerm(fields=["publication__title"], value="john doe")

        doi:10.1234/abc
            -> _PrefixedTerm(
                   fields=["publication__links__value"],
                   value="10.1234/abc",
                   extra=Q(publication__links__type__name="DOI"),
               )

    A bare ``10.1234/abc`` detected by the DOI alias produces the same term as
    ``doi:10.1234/abc``. ``term_query`` is copied from the alias when configured.
    """

    fields: list[str]
    value: str
    extra: Q = field(default_factory=Q)
    term_query: Callable[[str], Q] | None = None


@dataclass
class _PrefixedParseResult:
    """Result of extracting prefixed terms from a search string.

    Attributes:
        terms:     All recognised prefix:value terms found in the input.
        remaining: The input string with recognised prefixed terms removed,
                   ready for generic multi-field search.

    Example::

        'title:"a b" doi:10.1234/abc springer'
            -> terms=[
                   _PrefixedTerm(fields=["publication__title"], value="a b"),
                   _PrefixedTerm(
                       fields=["publication__links__value"],
                       value="10.1234/abc",
                       extra=Q(publication__links__type__name="DOI"),
                   ),
               ]
               remaining="springer"
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
        q &= _term_query(term)

    if result.remaining:
        phrases, words = _parse_search_terms(result.remaining)
        words = [word for word in words if word.lower() not in _STOP_WORDS]
        phrases = [phrase for phrase in phrases if phrase.strip()]
        detected, words = _detect_identifiers(words, field_aliases or {})
        for term in detected:
            q &= _term_query(term)
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
    normalized_aliases: dict[str, _NormalizedAlias] = {
        k: _normalise_alias(v) for k, v in aliases.items()
    }

    terms: list[_PrefixedTerm] = []

    def _replace(m: re.Match[str]) -> str:
        prefix = m.group(1)
        raw_value = m.group(2)
        if prefix in normalized_aliases:
            # Strip surrounding quotes if present
            value = raw_value.strip('"')
            alias = normalized_aliases[prefix]
            # Whitespace-only values carry no term; normalizers may reject them
            if alias.normalize is not None and value.strip():
                value = alias.normalize(value)
            if value.strip():
                terms.append(
                    _PrefixedTerm(
                        fields=alias.fields,
                        value=value,
                        extra=alias.extra,
                        term_query=alias.term_query,
                    )
                )
            return ""
        return m.group(0)

    remaining = _PREFIXED_TERM_RE.sub(_replace, search_term).strip()
    return _PrefixedParseResult(terms=terms, remaining=remaining)


def _term_query(term: _PrefixedTerm) -> Q:
    """Build the Q condition for one prefixed or detected term."""
    if term.term_query is not None:
        return term.term_query(term.value)
    return _match_any_field(term.value, term.fields) & term.extra


def _match_any_field(value: str, fields: Sequence[str]) -> Q:
    """Build a Q that matches value (case-insensitively) in at least one of the fields.

    Returns:
        A Q joining one ``icontains`` lookup per field with OR logic.
    """
    q = Q()
    for f in fields:
        q |= Q(**{f"{f}__icontains": value})
    return q


def _identifier_term(word: str, specs: Sequence[_NormalizedAlias]) -> _PrefixedTerm | None:
    """First scoped identifier term whose detector claims ``word``, if any."""
    for alias in specs:
        if alias.detect is None:
            continue
        value = alias.detect(word)
        if value is not None:
            return _PrefixedTerm(
                fields=alias.fields,
                value=value,
                extra=alias.extra,
                term_query=alias.term_query,
            )
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


def _normalise_alias(alias: str | list[str] | ScopedAlias) -> _NormalizedAlias:
    """Normalise any alias form to a ``_NormalizedAlias``."""
    if isinstance(alias, ScopedAlias):
        return _NormalizedAlias(
            fields=[alias.fields],
            extra=alias.extra,
            normalize=alias.normalize,
            detect=alias.detect,
            term_query=alias.term_query,
        )
    fields = [alias] if isinstance(alias, str) else alias
    return _NormalizedAlias(fields=fields)


def alias_field_paths(aliases: SearchFieldAliases) -> list[str]:
    """All field paths referenced by an alias mapping, in dict order, de-duplicated.

    Returns:
        The Django lookups referenced by every alias, flattened; a path shared by
        several aliases (e.g. contract link values scoped per link type) appears once.
    """
    paths = [path for alias in aliases.values() for path in _normalise_alias(alias).fields]
    return list(dict.fromkeys(paths))
