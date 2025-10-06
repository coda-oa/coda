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

    def __iter__(self) -> Generator[DomainModel, None, None]:
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
    def __getitem__(self, index: int) -> DomainModel:
        ...

    @overload
    def __getitem__(self, index: slice) -> list[DomainModel]:
        ...

    def __getitem__(self, index: int | slice) -> DomainModel | list[DomainModel]:
        if isinstance(index, slice):
            return [self.map_to_domain(model) for model in self.queryset[index]]

        return self.map_to_domain(self.queryset[index])
