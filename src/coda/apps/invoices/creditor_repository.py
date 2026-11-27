from collections.abc import Iterable

from coda.apps.invoices.models import Creditor
from coda.domain.finance.invoice import CreditorId


def get_or_create_creditors(names: Iterable[str]) -> dict[str, CreditorId]:
    """Resolve active creditors by name, creating missing ones in one batch."""
    unique_names = set(names)
    if not unique_names:
        return {}

    existing = Creditor.objects.filter(name__in=unique_names)
    lookup = {creditor.name: CreditorId(creditor.pk) for creditor in existing}

    missing = sorted(unique_names - lookup.keys())
    if missing:
        created = Creditor.objects.bulk_create([Creditor(name=name) for name in missing])
        lookup.update({creditor.name: CreditorId(creditor.pk) for creditor in created})

    return lookup
