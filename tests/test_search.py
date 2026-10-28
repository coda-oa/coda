"""Tests for coda.apps.search — build_search_filter and helpers."""

import pytest
from django.db.models import Q

from coda.apps.search import (
    ScopedAlias,
    _parse_prefixed_terms,
    _parse_search_terms,
    _PrefixedTerm,
    build_search_filter,
)


class TestParseSearchTerms:
    def test_empty_string(self) -> None:
        assert _parse_search_terms("") == ([], [])

    def test_only_whitespace(self) -> None:
        assert _parse_search_terms("   ") == ([], [])

    def test_single_word(self) -> None:
        assert _parse_search_terms("hello") == ([], ["hello"])

    def test_multiple_words(self) -> None:
        assert _parse_search_terms("hello world") == ([], ["hello", "world"])

    def test_leading_trailing_whitespace(self) -> None:
        assert _parse_search_terms("  hello world  ") == ([], ["hello", "world"])

    def test_quoted_phrase(self) -> None:
        assert _parse_search_terms('"mit press"') == (["mit press"], [])

    def test_quoted_phrase_with_leading_word(self) -> None:
        assert _parse_search_terms('"mit press" springer') == (["mit press"], ["springer"])

    def test_quoted_phrase_with_trailing_word(self) -> None:
        assert _parse_search_terms('springer "mit press"') == (["mit press"], ["springer"])

    def test_multiple_phrases(self) -> None:
        assert _parse_search_terms('"mit press" "springer nature"') == (
            ["mit press", "springer nature"],
            [],
        )

    def test_phrase_surrounded_by_words(self) -> None:
        assert _parse_search_terms('mit "press" springer') == (["press"], ["mit", "springer"])

    def test_unmatched_quote_treated_as_literal(self) -> None:
        assert _parse_search_terms('"mit press') == ([], ['"mit', "press"])

    def test_empty_quotes(self) -> None:
        assert _parse_search_terms('""') == ([""], [])


@pytest.mark.parametrize("query", ["", "   ", "\t"])
def test__empty_or_whitespace__returns_noop_q(query: str) -> None:
    assert build_search_filter(query, "title") == Q()


class TestBuildSearchFilterSingleField:
    def test_single_word(self) -> None:
        q = build_search_filter("hello", "title")
        assert q == Q(title__icontains="hello")

    def test_multiple_words(self) -> None:
        q = build_search_filter("hello world", "title")
        assert q == Q(title__icontains="hello") & Q(title__icontains="world")

    def test_quoted_phrase(self) -> None:
        q = build_search_filter('"hello world"', "title")
        assert q == Q(title__icontains="hello world")

    def test_phrase_and_word(self) -> None:
        q = build_search_filter('"hello world" foo', "title")
        assert q == Q(title__icontains="hello world") & Q(title__icontains="foo")


class TestBuildSearchFilterMultipleFields:
    def test_single_word_or_across_fields(self) -> None:
        q = build_search_filter("hello", "title", "author")
        assert q == Q(title__icontains="hello") | Q(author__icontains="hello")

    def test_multiple_words_and_across_groups(self) -> None:
        q = build_search_filter("hello world", "title", "author")
        expected = (Q(title__icontains="hello") | Q(author__icontains="hello")) & (
            Q(title__icontains="world") | Q(author__icontains="world")
        )
        assert q == expected

    def test_quoted_phrase_or_across_fields(self) -> None:
        q = build_search_filter('"hello world"', "title", "author")
        assert q == Q(title__icontains="hello world") | Q(author__icontains="hello world")


class TestBackwardCompatibility:
    """Without quotes, build_search_filter matches the original words_icontains behaviour."""

    def test_single_word(self) -> None:
        q1 = Q()
        q1 |= Q(title__icontains="hello")
        q1 |= Q(author__icontains="hello")

        q2 = build_search_filter("hello", "title", "author")
        assert q2 == q1

    def test_multiple_words(self) -> None:
        q1 = Q()
        word_q = Q()
        word_q |= Q(title__icontains="hello")
        word_q |= Q(author__icontains="hello")
        q1 &= word_q

        word_q = Q()
        word_q |= Q(title__icontains="world")
        word_q |= Q(author__icontains="world")
        q1 &= word_q

        q2 = build_search_filter("hello world", "title", "author")
        assert q2 == q1


class TestParsePrefixedTerms:
    def test_no_prefixes(self) -> None:
        result = _parse_prefixed_terms("hello world", {"author": ["author__name"]})
        assert result.terms == []
        assert result.remaining == "hello world"

    def test_quoted_prefixed_value(self) -> None:
        result = _parse_prefixed_terms('author:"john doe"', {"author": ["author__name"]})
        assert result.terms == [_PrefixedTerm(fields=["author__name"], value="john doe")]
        assert result.remaining == ""

    def test_unquoted_prefixed_value(self) -> None:
        result = _parse_prefixed_terms("author:john", {"author": ["author__name"]})
        assert result.terms == [_PrefixedTerm(fields=["author__name"], value="john")]
        assert result.remaining == ""

    def test_prefixed_and_unprefixed(self) -> None:
        result = _parse_prefixed_terms('author:"john" springer', {"author": ["author__name"]})
        assert result.terms == [_PrefixedTerm(fields=["author__name"], value="john")]
        assert result.remaining == "springer"

    def test_multiple_prefixed(self) -> None:
        result = _parse_prefixed_terms(
            'author:"john" title:foo',
            {"author": ["author__name"], "title": ["title"]},
        )
        assert result.terms == [
            _PrefixedTerm(fields=["author__name"], value="john"),
            _PrefixedTerm(fields=["title"], value="foo"),
        ]
        assert result.remaining == ""

    def test_unknown_prefix_left_as_literal(self) -> None:
        result = _parse_prefixed_terms("unknown:value", {"author": ["author__name"]})
        assert result.terms == []
        assert "unknown:value" in result.remaining

    def test_empty_quoted_value_skipped(self) -> None:
        result = _parse_prefixed_terms('author:""', {"author": ["author__name"]})
        assert result.terms == []
        assert result.remaining == ""


class TestBuildSearchFilterWithAliases:
    def test_single_prefixed_quoted(self) -> None:
        q = build_search_filter(
            'author:"john doe"', "title", "author__name", field_aliases={"author": "author__name"}
        )
        assert q == Q(author__name__icontains="john doe")

    def test_prefixed_and_unprefixed_terms(self) -> None:
        q = build_search_filter(
            'author:"john" springer',
            "title",
            "author__name",
            field_aliases={"author": "author__name"},
        )
        expected = Q(author__name__icontains="john") & (
            Q(title__icontains="springer") | Q(author__name__icontains="springer")
        )
        assert q == expected

    def test_multiple_prefixed(self) -> None:
        q = build_search_filter(
            'author:"john" title:foo',
            "title",
            "author__name",
            field_aliases={"author": "author__name", "title": "title"},
        )
        assert q == Q(author__name__icontains="john") & Q(title__icontains="foo")

    def test_prefixed_can_be_multi_field(self) -> None:
        q = build_search_filter(
            'publisher:"springer"',
            "title",
            field_aliases={"publisher": ["j_pub", "m_pub"]},
        )
        assert q == Q(j_pub__icontains="springer") | Q(m_pub__icontains="springer")

    def test_unprefixed_no_aliases_behaviour_unchanged(self) -> None:
        """When field_aliases is None, prefixed terms are treated as literal text."""
        q = build_search_filter("author:john", "title")
        assert q == Q(title__icontains="author:john")

    def test_terms_phrases_and_words_combined(self) -> None:
        """AND order is preserved: prefixed terms, then phrases, then words."""
        q = build_search_filter(
            'author:a "b c" d',
            "title",
            "author__name",
            field_aliases={"author": "author__name"},
        )
        expected = (
            Q(author__name__icontains="a")
            & (Q(title__icontains="b c") | Q(author__name__icontains="b c"))
            & (Q(title__icontains="d") | Q(author__name__icontains="d"))
        )
        assert q == expected


class TestScopedAlias:
    def test_parse_scoped_alias(self) -> None:
        extra = Q(publication__links__type__name="DOI")
        result = _parse_prefixed_terms(
            "doi:10.1234/abc",
            {"doi": ScopedAlias("publication__links__value", extra)},
        )
        assert result.terms == [
            _PrefixedTerm(
                fields=["publication__links__value"],
                value="10.1234/abc",
                extra=extra,
            )
        ]
        assert result.remaining == ""

    def test_scoped_single_field_q_shape(self) -> None:
        extra = Q(publication__links__type__name="DOI")
        q = build_search_filter(
            "doi:10.1234/abc",
            "title",
            field_aliases={"doi": ScopedAlias("publication__links__value", extra)},
        )
        assert q == Q(publication__links__value__icontains="10.1234/abc") & extra



    def test_scoped_plain_and_word_terms_order(self) -> None:
        """Scoped term (with extra filter) comes before generic words in AND order."""
        extra = Q(publication__links__type__name="DOI")
        q = build_search_filter(
            'doi:"10.1234/abc" springer',
            "title",
            "author__name",
            field_aliases={"doi": ScopedAlias("publication__links__value", extra)},
        )
        expected = (
            Q(publication__links__value__icontains="10.1234/abc")
            & extra
            & (Q(title__icontains="springer") | Q(author__name__icontains="springer"))
        )
        assert q == expected


class TestStopWords:
    def test_stop_word_word_is_dropped(self) -> None:
        """'and' as a word carries no weight; other words still AND."""
        q = build_search_filter("wiley and sons", "name")
        assert q == Q(name__icontains="wiley") & Q(name__icontains="sons")

    def test_ampersand_word_is_dropped(self) -> None:
        q = build_search_filter("wiley & sons", "name")
        assert q == Q(name__icontains="wiley") & Q(name__icontains="sons")

    def test_case_insensitive_stop_word(self) -> None:
        q = build_search_filter("Wiley AND Sons", "name")
        assert q == Q(name__icontains="Wiley") & Q(name__icontains="Sons")

    def test_quoted_phrase_keeps_conjunction(self) -> None:
        """Quotes mean exact: the phrase is searched literally, stop-word-free."""
        q = build_search_filter('"wiley and sons"', "name")
        assert q == Q(name__icontains="wiley and sons")

    def test_quoted_ampersand_phrase_keeps_ampersand(self) -> None:
        q = build_search_filter('"wiley & sons"', "name")
        assert q == Q(name__icontains="wiley & sons")

    def test_prefix_value_keeps_conjunction(self) -> None:
        q = build_search_filter(
            'title:"rock and roll"',
            "title",
            field_aliases={"title": "title"},
        )
        assert q == Q(title__icontains="rock and roll")

    def test_stop_word_inside_larger_word_is_kept(self) -> None:
        q = build_search_filter("sandwich", "name")
        assert q == Q(name__icontains="sandwich")

    def test_rd_literal_is_kept(self) -> None:
        """& inside a word is not a stop word; the word is searched literally."""
        q = build_search_filter("R&D Systems", "name")
        assert q == Q(name__icontains="R&D") & Q(name__icontains="Systems")

    def test_only_stop_words_falls_back_to_literal(self) -> None:
        """A stop-word-only query must not match every row."""
        q = build_search_filter("and", "name")
        assert q == Q(name__icontains="and")

    def test_only_ampersand_falls_back_to_literal(self) -> None:
        q = build_search_filter("&", "name")
        assert q == Q(name__icontains="&")

    def test_stop_words_and_phrase_mixed(self) -> None:
        q = build_search_filter('"rock and roll" and springer', "name")
        expected = Q(name__icontains="rock and roll") & Q(name__icontains="springer")
        assert q == expected

    def test_precision_widens_without_conjunction_requirement(self) -> None:
        """Words AND without requiring a conjunction to exist anywhere."""
        q = build_search_filter("lancet and child", "name")
        assert q == Q(name__icontains="lancet") & Q(name__icontains="child")
