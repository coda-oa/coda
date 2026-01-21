import pytest
from typing import Any
from django.db.models import QuerySet

from coda.apps.domainqueryset import LazyBulkQuerySet
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from tests import modelfactory


@pytest.mark.django_db
@pytest.mark.integration
class TestLazyBulkQuerySet:
    """Test suite for LazyBulkQuerySet lazy evaluation and bulk conversion."""

    def test__len__returns_queryset_count_without_fetching_items(
        self, django_assert_num_queries: Any
    ) -> None:
        """Verify len() only does a COUNT query, doesn't fetch items."""
        for _ in range(50):
            modelfactory.fundingrequest()

        queryset = FundingRequestModel.objects.all()
        lazy_qs = LazyBulkQuerySet(
            queryset=queryset,
            bulk_converter=lambda qs: list(qs),
        )

        with django_assert_num_queries(1):
            result = len(lazy_qs)

        assert result == 50

    def test__getitem_slice__only_fetches_requested_slice(
        self, django_assert_num_queries: Any
    ) -> None:
        """Verify slicing only fetches the requested items, not all items."""
        for _ in range(100):
            modelfactory.fundingrequest()

        queryset = FundingRequestModel.objects.all().order_by("id")

        converted_counts = []

        def tracking_converter(qs: QuerySet[FundingRequestModel]) -> list[int]:
            items = list(qs)
            converted_counts.append(len(items))
            return [item.pk for item in items]

        lazy_qs = LazyBulkQuerySet(
            queryset=queryset,
            bulk_converter=tracking_converter,
        )

        with django_assert_num_queries(1):
            result = lazy_qs[10:20]

        assert len(result) == 10
        assert converted_counts == [10]

    def test__getitem_single__returns_single_item(self) -> None:
        """Verify single item access returns one item."""
        modelfactory.fundingrequest()
        fr2 = modelfactory.fundingrequest()
        modelfactory.fundingrequest()

        queryset = FundingRequestModel.objects.all().order_by("id")
        lazy_qs = LazyBulkQuerySet(
            queryset=queryset,
            bulk_converter=lambda qs: [item.pk for item in qs],
        )

        result = lazy_qs[1]

        assert result == fr2.pk

    def test__getitem_single__raises_index_error_when_out_of_range(self) -> None:
        """Verify single item access raises IndexError when index is invalid."""
        modelfactory.fundingrequest()

        queryset = FundingRequestModel.objects.all()
        lazy_qs = LazyBulkQuerySet(
            queryset=queryset,
            bulk_converter=lambda qs: list(qs),
        )

        with pytest.raises(IndexError, match="list index out of range"):
            _ = lazy_qs[10]

    def test__iter__processes_all_items_in_chunks(self) -> None:
        """Verify iteration processes all items in configurable chunks."""
        for _ in range(250):
            modelfactory.fundingrequest()

        queryset = FundingRequestModel.objects.all().order_by("id")

        chunk_sizes = []

        def tracking_converter(qs: QuerySet[FundingRequestModel]) -> list[int]:
            items = list(qs)
            chunk_sizes.append(len(items))
            return [item.pk for item in items]

        lazy_qs = LazyBulkQuerySet(
            queryset=queryset,
            bulk_converter=tracking_converter,
            chunk_size=100,
        )

        all_items = list(lazy_qs)

        assert chunk_sizes == [100, 100, 50]
        assert len(all_items) == 250

    def test__iter__with_custom_chunk_size(self) -> None:
        """Verify custom chunk size is respected during iteration."""
        for _ in range(100):
            modelfactory.fundingrequest()

        queryset = FundingRequestModel.objects.all().order_by("id")

        chunk_sizes = []

        def tracking_converter(qs: QuerySet[FundingRequestModel]) -> list[int]:
            items = list(qs)
            chunk_sizes.append(len(items))
            return [item.pk for item in items]

        lazy_qs = LazyBulkQuerySet(
            queryset=queryset,
            bulk_converter=tracking_converter,
            chunk_size=25,
        )

        all_items = list(lazy_qs)

        assert chunk_sizes == [25, 25, 25, 25]
        assert len(all_items) == 100

    def test__empty_queryset__returns_empty_results(self) -> None:
        """Verify empty queryset behaves correctly."""
        queryset = FundingRequestModel.objects.none()
        lazy_qs = LazyBulkQuerySet(
            queryset=queryset,
            bulk_converter=lambda qs: list(qs),
        )

        assert len(lazy_qs) == 0
        assert lazy_qs[0:10] == []
        assert list(lazy_qs) == []

    def test__pagination_compatibility__works_with_django_paginator(self) -> None:
        """Verify LazyBulkQuerySet works correctly with Django's Paginator."""
        from django.core.paginator import Paginator

        items = [modelfactory.fundingrequest() for _ in range(45)]

        queryset = FundingRequestModel.objects.all().order_by("id")
        lazy_qs = LazyBulkQuerySet(
            queryset=queryset,
            bulk_converter=lambda qs: [item.pk for item in qs],
        )

        paginator = Paginator(lazy_qs, per_page=10)

        assert paginator.num_pages == 5

        page1 = paginator.get_page(1)
        assert len(page1.object_list) == 10
        assert page1.object_list[0] == items[0].pk

        page3 = paginator.get_page(3)
        assert len(page3.object_list) == 10
        assert page3.object_list[0] == items[20].pk

        page5 = paginator.get_page(5)
        assert len(page5.object_list) == 5
        assert page5.object_list[0] == items[40].pk

    def test__bulk_converter_is_called_with_sliced_queryset(self) -> None:
        """Verify bulk_converter receives the correct sliced queryset."""
        for _ in range(50):
            modelfactory.fundingrequest()

        queryset = FundingRequestModel.objects.all().order_by("id")

        received_querysets = []

        def tracking_converter(qs: QuerySet[FundingRequestModel]) -> list[str]:
            received_querysets.append(str(qs.query))
            return [f"item_{item.pk}" for item in qs]

        lazy_qs = LazyBulkQuerySet(
            queryset=queryset,
            bulk_converter=tracking_converter,
        )

        result = lazy_qs[10:20]

        assert len(received_querysets) == 1
        assert len(result) == 10
        assert all(item.startswith("item_") for item in result)

    def test__contains__returns_true_for_existing_item(self) -> None:
        """Verify __contains__ correctly identifies existing items."""
        fr1 = modelfactory.fundingrequest()
        fr2 = modelfactory.fundingrequest()
        fr3 = modelfactory.fundingrequest()

        queryset = FundingRequestModel.objects.filter(id__in=[fr1.pk, fr2.pk])
        lazy_qs = LazyBulkQuerySet(
            queryset=queryset,
            bulk_converter=lambda qs: list(qs),
        )

        assert fr1 in lazy_qs
        assert fr2 in lazy_qs
        assert fr3 not in lazy_qs
