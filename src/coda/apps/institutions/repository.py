from collections.abc import Container, Iterable

from django.db.models import QuerySet

from coda.apps.institutions.models import Institution


def create(name: str, parent: Institution | None = None) -> Institution:
    return Institution.objects.create(name=name, parent=parent)


def get_by_id(id: int) -> Institution:
    return Institution.all_objects.get(pk=id)


def get_many_by_id(ids: Container[int]) -> Iterable[Institution]:
    return Institution.objects.filter(id__in=ids)


def all() -> Iterable[Institution]:
    roots = Institution.objects.filter(parent=None)
    yield from (institution for root in roots for institution in root.walk())


def non_virtuals() -> Iterable[Institution]:
    return Institution.objects.filter(virtual=False)


def first_by_name(name: str) -> Institution | None:
    return Institution.objects.filter(name=name).first()


def search(name: str | None = None, include_archived: bool = False) -> QuerySet[Institution]:
    if include_archived:
        qs = Institution.all_objects.all()
    else:
        qs = Institution.objects.all()

    if name is not None:
        qs = qs.filter(name__icontains=name)

    return qs.order_by("parent__name", "name")


def archived_only() -> QuerySet[Institution]:
    return Institution.objects.archived_only()
