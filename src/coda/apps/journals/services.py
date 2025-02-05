from collections.abc import Sequence

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.journals.models import Journal
from coda.issn import Issn


def get_by_pk(pk: int) -> Journal:
    return Journal.objects.get(pk=pk)


def all() -> Sequence[Journal]:
    return DomainQuerySet(Journal.objects.all().order_by("title"), _map_self)


def find_by_title(title: str) -> Sequence[Journal]:
    return DomainQuerySet(
        Journal.objects.filter(title__icontains=title).order_by("title"), _map_self
    )


def find_by_eissn(eissn: Issn) -> Sequence[Journal]:
    return DomainQuerySet(Journal.objects.filter(eissn=eissn), _map_self)


def _map_self(journal: Journal) -> Journal:
    return journal
