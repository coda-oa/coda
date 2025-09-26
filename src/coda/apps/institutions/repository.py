from collections.abc import Iterable
from coda.apps.institutions.models import Institution


def create(name: str, parent: Institution | None = None) -> Institution:
    return Institution.objects.create(name=name, parent=parent)


def get_by_id(id: int) -> Institution:
    return Institution.objects.get(pk=id)


def all() -> Iterable[Institution]:
    roots = Institution.objects.filter(parent=None)
    yield from (institution for root in roots for institution in root.walk())


def non_virtuals() -> Iterable[Institution]:
    return Institution.objects.filter(virtual=False)


def first_by_name(name: str) -> Institution | None:
    return Institution.objects.filter(name=name).first()


def search(name: str | None = None) -> Iterable[Institution]:
    if name is None:
        return all()

    return Institution.objects.filter(name__icontains=name).order_by("parent__name", "name")
