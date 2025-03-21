from collections.abc import Sequence

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.journals.models import Journal
from coda.contract import PublisherId
from coda.issn import Issn
from coda.publication import JournalId
from coda.string import NonEmptyStr


def create(title: NonEmptyStr, eissn: Issn, publisher_id: PublisherId) -> JournalId:
    journal = Journal.objects.create(title=title, eissn=eissn, publisher_id=publisher_id)
    return JournalId(journal.pk)


def get_by_pk(pk: int) -> Journal:
    return Journal.objects.get(pk=pk)


def all() -> Sequence[Journal]:
    return DomainQuerySet(Journal.objects.all().order_by("title"), _map_self)


def find_by_title(title: str) -> Sequence[Journal]:
    return DomainQuerySet(
        Journal.objects.filter(title__icontains=title).order_by("title"), _map_self
    )


def find_by_eissn(eissn: Issn) -> Journal | None:
    return Journal.objects.filter(eissn=eissn).first()


def eissn_for(pk: int) -> Issn:
    return Issn(Journal.objects.filter(pk=pk).values_list("eissn", flat=True).get())


def _map_self(journal: Journal) -> Journal:
    return journal
