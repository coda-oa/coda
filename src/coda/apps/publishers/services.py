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
