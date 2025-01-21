from collections.abc import Iterable
from coda.apps.institutions.models import Institution


def get_by_id(id: int) -> Institution:
    return Institution.objects.get(pk=id)


def all() -> Iterable[Institution]:
    roots = Institution.objects.filter(parent=None)
    yield from (institution for root in roots for institution in root.walk())


def non_virtuals() -> Iterable[Institution]:
    return Institution.objects.filter(virtual=False)


def search(name: str | None = None) -> Iterable[Institution]:
    if name is None:
        return all()

    return Institution.objects.filter(name__icontains=name).order_by("parent__name", "name")
