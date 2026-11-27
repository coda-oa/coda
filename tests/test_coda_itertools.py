from coda.coda_itertools import LazyCachedIterable


def test__factory__resolved_once_after_first_use_only() -> None:
    calls: list[int] = []

    def factory() -> list[int]:
        calls.append(1)
        return [1, 2, 3]

    lazy = LazyCachedIterable(factory)

    assert calls == []  # the whole point of the class: nothing resolved yet
    assert bool(lazy) is True
    assert list(lazy) == [1, 2, 3]
    assert list(lazy) == [1, 2, 3]
    assert calls == [1]


def test__generator_argument__is_still_supported() -> None:
    lazy = LazyCachedIterable(x for x in (1, 2, 3))

    assert list(lazy) == [1, 2, 3]
    assert list(lazy) == [1, 2, 3]


def test__partial_iteration_then_full_iteration__yields_no_duplicates() -> None:
    calls: list[int] = []

    def factory() -> list[int]:
        calls.append(1)
        return [1, 2, 3]

    lazy = LazyCachedIterable(factory)

    assert calls == []
    assert next(iter(lazy)) == 1
    assert list(lazy) == [1, 2, 3]
    assert list(lazy) == [1, 2, 3]
    assert calls == [1]


def test__empty_source__is_falsy_and_iterates_to_empty() -> None:
    calls: list[int] = []

    def factory() -> list[int]:
        calls.append(1)
        return []

    lazy = LazyCachedIterable(factory)

    assert calls == []
    assert not lazy
    assert list(lazy) == []
    assert calls == [1]


def test__bool_after_full_iteration_of_empty__stays_false_without_refetch() -> None:
    calls: list[int] = []

    def factory() -> list[int]:
        calls.append(1)
        return []

    lazy = LazyCachedIterable(factory)

    assert list(lazy) == []
    assert bool(lazy) is False
    assert bool(lazy) is False
    assert calls == [1]


def test__bool_on_partially_consumed_non_empty__is_true_without_extra_pull() -> None:
    calls: list[int] = []

    def factory() -> list[int]:
        calls.append(1)
        return [1, 2, 3]

    lazy = LazyCachedIterable(factory)

    assert next(iter(lazy)) == 1
    assert bool(lazy) is True
    assert list(lazy) == [1, 2, 3]
    assert calls == [1]


def test__bool_after_full_consumption_of_non_empty__is_true_without_refetch() -> None:
    calls: list[int] = []

    def factory() -> list[int]:
        calls.append(1)
        return [1, 2]

    lazy = LazyCachedIterable(factory)

    assert list(lazy) == [1, 2]
    assert bool(lazy) is True
    assert bool(lazy) is True
    assert calls == [1]
