from django.db.models import QuerySet

from coda.apps.publishers.models import Publisher
from coda.domain.contract import PublisherId


def find_by_name(name: str) -> Publisher | None:
    """
    Find a publisher by name with case-insensitive matching.

    Args:
        name: The publisher name to search for (whitespace will be trimmed)

    Returns:
        Publisher instance if found, None otherwise
    """
    trimmed_name = name.strip()
    try:
        return Publisher.objects.get(name__iexact=trimmed_name)
    except Publisher.DoesNotExist:
        return None


def find_by_name_contains(name: str) -> "QuerySet[Publisher]":
    """
    Find publishers whose name contains the given string (case-insensitive), sorted by name.

    Args:
        name: The substring to search for within publisher names

    Returns:
        QuerySet of Publisher instances ordered by name
    """
    return Publisher.objects.filter(name__icontains=name).order_by("name")


def get_by_pk(pk: int) -> Publisher:
    return Publisher.objects.get(pk=pk)


def create(name: str) -> PublisherId:
    """
    Create a new publisher.

    Args:
        name: The publisher name (whitespace will be trimmed)

    Returns:
        PublisherId of the newly created publisher
    """
    trimmed_name = name.strip()
    publisher = Publisher.objects.create(name=trimmed_name)
    return PublisherId(publisher.pk)
