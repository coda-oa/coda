from collections.abc import Callable, Generator, Sequence
from typing import Any, Generic, Protocol, TypeVar, cast, overload, runtime_checkable
from django.db import models


IntLike = TypeVar("IntLike", bound=int)


@runtime_checkable
class MaybeUnitializedDomainModelProtocol(Protocol, Generic[IntLike]):
    id: IntLike | None


@runtime_checkable
class DomainModelProtocol(Protocol, Generic[IntLike]):
    id: IntLike


DjangoModel = TypeVar("DjangoModel", bound=models.Model)

# NOTE: Using Any here is a workaround, because NewTypes based on int are not considered subclasses of int in Protocols.
# We therefore, we created a TypeVar bound to int, and used it as a type hint for the DomainModelProtocol.
# DomainModelProtocol[Any] loses the ability to type check the exact type of the id attribute, but it's a trade-off we're willing to make.
DomainModel = TypeVar(
    "DomainModel",
    bound=DomainModelProtocol[Any] | MaybeUnitializedDomainModelProtocol[Any] | models.Model,
)


class DomainQuerySet(Generic[DjangoModel, DomainModel], Sequence[DomainModel]):
    """
    DomainQuerySet is a wrapper around a Django QuerySet that maps the Django models to domain models.
    It is used to avoid iterate and convert the models eagerly, and instead do it lazily.
    """

    def __init__(
        self,
        queryset: models.QuerySet[DjangoModel],
        map_to_domain: Callable[[DjangoModel], DomainModel],
    ) -> None:
        self.queryset = queryset
        self.map_to_domain = map_to_domain

    def __len__(self) -> int:
        return self.queryset.count()

    def __iter__(self) -> Generator[DomainModel]:
        yield from (self.map_to_domain(model) for model in self.queryset.iterator(chunk_size=2000))

    def __contains__(self, item: object) -> bool:
        if not isinstance(
            item, (DomainModelProtocol, MaybeUnitializedDomainModelProtocol, models.Model)
        ):
            return False

        id = self._get_id(cast(DomainModel, item))
        if not id:
            return False

        return self.queryset.filter(id=id).exists()

    def _get_id(self, item: DomainModel) -> int | None:
        if isinstance(item, models.Model):
            return int(item.pk)

        return item.id

    @overload
    def __getitem__(self, index: int) -> DomainModel: ...

    @overload
    def __getitem__(self, index: slice) -> list[DomainModel]: ...

    def __getitem__(self, index: int | slice) -> DomainModel | list[DomainModel]:
        if isinstance(index, slice):
            return [self.map_to_domain(model) for model in self.queryset[index]]

        return self.map_to_domain(self.queryset[index])


ResultType = TypeVar("ResultType")


class LazyBulkQuerySet(Generic[DjangoModel, ResultType], Sequence[ResultType]):
    """
    Lazy wrapper for bulk-converting Django QuerySets to domain/view models.

    Unlike DomainQuerySet which maps items one-by-one, this class accepts
    a bulk converter function that can perform optimizations (like bulk
    fetching related data) when converting a slice of the queryset.

    This is particularly useful for list views where you want to:
    - Avoid N+1 queries by bulk-fetching related data
    - Only process the current page being viewed
    - Maintain Django pagination compatibility

    Example:
        >>> def bulk_convert(qs: QuerySet[FundingRequest]) -> list[FundingRequestListItem]:
        ...     # Bulk fetch payment statuses for all items in qs
        ...     publication_ids = [fr.publication_id for fr in qs]
        ...     payment_statuses = fetch_payment_statuses_bulk(publication_ids)
        ...     return [build_list_item(fr, payment_statuses) for fr in qs]
        >>>
        >>> lazy_qs = LazyBulkQuerySet(
        ...     queryset=FundingRequest.objects.all(), bulk_converter=bulk_convert, chunk_size=100
        ... )
        >>> page_items = lazy_qs[0:10]  # Only converts 10 items with bulk optimization
        >>> # Result: 5 queries instead of 21 queries (N+1 problem avoided)

    Args:
        queryset: Django QuerySet to wrap
        bulk_converter: Function that takes a QuerySet and returns a list of results.
                       This function should perform any necessary bulk fetching.
        chunk_size: Size of chunks for iteration (default: 100). Used when iterating
                   through all items to balance query count vs memory usage.
    """

    def __init__(
        self,
        queryset: models.QuerySet[DjangoModel],
        bulk_converter: Callable[[models.QuerySet[DjangoModel]], list[ResultType]],
        chunk_size: int = 100,
    ) -> None:
        self._queryset = queryset
        self._bulk_converter = bulk_converter
        self._chunk_size = chunk_size

    def __len__(self) -> int:
        """
        Return the count of items without fetching them.

        Used by Django's Paginator to determine total pages.
        """
        return self._queryset.count()

    @overload
    def __getitem__(self, index: int) -> ResultType: ...

    @overload
    def __getitem__(self, index: slice) -> list[ResultType]: ...

    def __getitem__(self, index: int | slice) -> ResultType | list[ResultType]:
        """
        Get item(s) by index or slice, applying bulk conversion.

        This is the key method for pagination - when Paginator requests
        entities[0:10], we only convert those 10 items with bulk optimization.

        Args:
            index: Integer for single item or slice for multiple items

        Returns:
            Single item if index is int, list of items if index is slice

        Raises:
            IndexError: If single item index is out of range
        """
        if isinstance(index, slice):
            # Paginator requests a slice (e.g., [0:10] for page 1)
            sliced_qs = self._queryset[index]
            return self._bulk_converter(sliced_qs)
        else:
            # Single item access - still use bulk converter for consistency
            # This could be optimized if single-item access becomes common
            sliced_qs = self._queryset[index : index + 1]
            items = self._bulk_converter(sliced_qs)
            if not items:
                raise IndexError("list index out of range")
            return items[0]

    def __iter__(self) -> Generator[ResultType]:
        """
        Iterate over all items in chunks, applying bulk conversion per chunk.

        This is more efficient than item-by-item iteration when the caller
        needs to process all items (e.g., export functionality, full iteration).

        The chunk size balances query count vs memory usage:
        - Larger chunks: Fewer queries, more memory
        - Smaller chunks: More queries, less memory

        Yields:
            Individual items from the queryset
        """
        total = len(self)
        for start in range(0, total, self._chunk_size):
            end = min(start + self._chunk_size, total)
            chunk_qs = self._queryset[start:end]
            yield from self._bulk_converter(chunk_qs)

    def __contains__(self, item: object) -> bool:
        """
        Check if an item exists in the queryset.

        Note: This implementation assumes items have an 'id' attribute.
        If the item is a domain model or has an ID, we check if that ID
        exists in the queryset.

        Args:
            item: Object to check for membership

        Returns:
            True if item exists in queryset, False otherwise
        """
        # Try to get ID from domain models, view models, or Django models
        if isinstance(item, models.Model):
            item_id = item.pk
        elif hasattr(item, "id"):
            item_id = getattr(item, "id")
        else:
            return False

        if item_id is None:
            return False

        return self._queryset.filter(id=item_id).exists()
