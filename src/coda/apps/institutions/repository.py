from collections.abc import Container, Iterable

from django.db.models import Case, IntegerField, QuerySet, When

from coda.apps.institutions.models import Institution
from coda.apps.search import words_icontains


def create(name: str, parent: Institution | None = None) -> Institution:
    return Institution.objects.create(name=name, parent=parent)


def get_by_id(id: int) -> Institution:
    return Institution.all_objects.get(pk=id)


def get_many_by_id(ids: Container[int]) -> Iterable[Institution]:
    return Institution.all_objects.filter(pk__in=ids).distinct()


def all() -> Iterable[Institution]:
    roots = Institution.objects.filter(parent=None)
    yield from (institution for root in roots for institution in root.walk())


def non_virtuals() -> Iterable[Institution]:
    return Institution.objects.filter(virtual=False)


def active_non_virtuals() -> Iterable[Institution]:
    return Institution.objects.filter(virtual=False, archived_at__isnull=True)


def first_by_name(name: str) -> Institution | None:
    return Institution.objects.filter(name=name).first()


def search(name: str | None = None, include_archived: bool = False) -> QuerySet[Institution]:
    qs: QuerySet[Institution]
    if include_archived:
        qs = Institution.all_objects.all()
    else:
        qs = Institution.objects.all()

    if name is not None:
        qs = qs.filter(words_icontains(name, "name"))

    return _sort_hierarchically(qs)


def archived_only() -> QuerySet[Institution]:
    return Institution.objects.archived_only()


def _get_hierarchical_sort_path(institution: Institution) -> tuple[str, ...]:
    path: list[str] = []
    current: Institution | None = institution
    while current is not None:
        path.insert(0, current.name.lower())
        current = current.parent
    return tuple(path)


def _sort_hierarchically(queryset: QuerySet[Institution]) -> QuerySet[Institution]:
    institutions = list(
        queryset.select_related(
            "parent",
            "parent__parent",
            "parent__parent__parent",
            "parent__parent__parent__parent",
            "parent__parent__parent__parent__parent",
            "parent__parent__parent__parent__parent__parent",
        )
    )

    institutions.sort(key=_get_hierarchical_sort_path)

    if institutions:
        id_order = {inst.pk: idx for idx, inst in enumerate(institutions)}
        preserved_order = Case(
            *[When(pk=pk, then=pos) for pk, pos in id_order.items()],
            output_field=IntegerField(),
        )
        return queryset.filter(id__in=id_order.keys()).order_by(preserved_order)

    return queryset
