import logging

from django.db.models import QuerySet

from coda.apps.publishers.models import Publisher
from coda.apps.search import build_search_filter
from coda.domain.contract import PublisherId

logger = logging.getLogger(__name__)


def find_by_name(name: str) -> Publisher | None:
    """
    Find a publisher by name with case-insensitive matching.

    Args:
        name: The publisher name to search for (whitespace will be trimmed)

    Returns:
        Publisher instance if found, None otherwise

    Note:
        If multiple publishers match (e.g. "Elsevier" and "elsevier"), the
        first match is returned and a warning is logged.  The caller should
        use ``find_by_name_contains`` when duplicates are expected.
    """
    trimmed_name = name.strip()
    try:
        return Publisher.objects.get(name__iexact=trimmed_name)
    except Publisher.DoesNotExist:
        return None
    except Publisher.MultipleObjectsReturned:
        logger.warning(
            "Multiple publishers match name '%s' (case-insensitive); returning first.",
            trimmed_name,
        )
        return Publisher.objects.filter(name__iexact=trimmed_name).first()


def find_by_name_contains(name: str) -> "QuerySet[Publisher]":
    """
    Find publishers whose name contains the given string (case-insensitive), sorted by name.

    Args:
        name: The substring to search for within publisher names

    Returns:
        QuerySet of Publisher instances ordered by name
    """
    return Publisher.objects.filter(build_search_filter(name, "name")).order_by("name")


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
