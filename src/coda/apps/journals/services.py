from django.db.models import QuerySet

from coda.apps.journals.models import Journal
from coda.issn import Issn


def get_by_pk(pk: int) -> Journal:
    return Journal.objects.get(pk=pk)


def find_by_title(title: str) -> QuerySet[Journal]:
    return Journal.objects.filter(title__icontains=title).order_by("title")


def find_by_eissn(eissn: Issn) -> QuerySet[Journal]:
    return Journal.objects.filter(eissn=eissn)
