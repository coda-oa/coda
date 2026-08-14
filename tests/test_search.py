"""Tests for coda.apps.search — build_search_filter and helpers."""

import pytest
from django.db.models import Q

from coda.apps.search import _parse_search_terms, build_search_filter


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
        phrases, words = _parse_search_terms('"mit press')
        assert phrases == []
        assert '"mit' in words
        assert 'press"' in words or "press" in words

    def test_empty_quotes(self) -> None:
        assert _parse_search_terms('""') == ([""], [])


@pytest.mark.parametrize("query", ["", "   ", "\t"])
def test__empty_or_whitespace__returns_noop_q(query: str) -> None:
    assert build_search_filter(query, "title") == Q()


class TestBuildSearchFilterSingleField:
    def test_single_word(self) -> None:
        q = build_search_filter("hello", "title")
        assert repr(q) == "<Q: (AND: ('title__icontains', 'hello'))>"

    def test_multiple_words(self) -> None:
        q = build_search_filter("hello world", "title")
        assert repr(q) == (
            "<Q: (AND: ('title__icontains', 'hello'), ('title__icontains', 'world'))>"
        )

    def test_quoted_phrase(self) -> None:
        q = build_search_filter('"hello world"', "title")
        assert repr(q) == "<Q: (AND: ('title__icontains', 'hello world'))>"

    def test_phrase_and_word(self) -> None:
        q = build_search_filter('"hello world" foo', "title")
        assert repr(q) == (
            "<Q: (AND: ('title__icontains', 'hello world'), "
            "('title__icontains', 'foo'))>"
        )


class TestBuildSearchFilterMultipleFields:
    def test_single_word_or_across_fields(self) -> None:
        q = build_search_filter("hello", "title", "author")
        assert repr(q) == (
            "<Q: (OR: ('title__icontains', 'hello'), ('author__icontains', 'hello'))>"
        )

    def test_multiple_words_and_across_groups(self) -> None:
        q = build_search_filter("hello world", "title", "author")
        assert repr(q) == (
            "<Q: (AND: (OR: ('title__icontains', 'hello'), ('author__icontains', 'hello')), "
            "(OR: ('title__icontains', 'world'), ('author__icontains', 'world')))>"
        )

    def test_quoted_phrase_or_across_fields(self) -> None:
        q = build_search_filter('"hello world"', "title", "author")
        assert repr(q) == (
            "<Q: (OR: ('title__icontains', 'hello world'), "
            "('author__icontains', 'hello world'))>"
        )


class TestBackwardCompatibility:
    """Without quotes, build_search_filter matches the original words_icontains behaviour."""

    def test_single_word(self) -> None:
        q1 = Q()
        q1 |= Q(title__icontains="hello")
        q1 |= Q(author__icontains="hello")

        q2 = build_search_filter("hello", "title", "author")
        assert repr(q2) == repr(q1)

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
        assert repr(q2) == repr(q1)
