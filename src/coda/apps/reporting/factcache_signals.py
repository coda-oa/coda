"""Cache invalidation for the statistics fact set.

Every model the statistics fetch graph reads
(``apps/reporting/queries.py``) bumps the facts generation on write. A
missed write path shows stale money until the TTL expires, so the model
list here must cover the whole graph: the request itself (and its review —
a review status is a filter criterion), its publication and every entity
the prefetches walk (positions, invoices, conversions, funding assignments
and sources plus their institutions, corresponding authors and their
affiliations, attached contracts, publication types,
external funding and its organization, journals and publishers, contracts,
creditors, labels, links, vocabularies and concepts). The export fetch
(``apps/exports/services/fundingrequest_csv/queries.py``) reads a
superset, so it is covered too.

Known limit: ``bulk_create`` and ``bulk_update`` do not fire ``post_save``
or ``post_delete``. The bulk write paths therefore call
``factcache.bump_generation()`` directly, next to the write. These paths
are: invoice ``create_many`` (``apps/invoices/repository.py``),
funding-request import (``apps/fundingrequests/repository.py``), author
import (``apps/authors/services.py``), contract import
(``apps/contracts/repository.py``), publication payment updates
(``apps/publications/repositories/payment_repository.py``), and the
institution bulk methods (``apps/institutions/models.py``). The signal
receivers cover single-row saves and deletes. The TTL bounds the staleness
if a new bulk path forgets the bump."""

from django.db.models import Model
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from coda.apps.authors.models import Author
from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.models import (
    ExternalFunding,
    FundingOrganization,
    FundingRequest,
    FundingRequestReview,
    Label,
)
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import (
    Creditor,
    CurrencyConversion,
    FundingAssignment,
    FundingSource,
    Invoice,
    Position,
)
from coda.apps.journals.models import Journal
from coda.apps.publications.models import (
    AttachedContract,
    Concept,
    Link,
    Publication,
    PublicationPayment,
)
from coda.apps.publishers.models import Publisher
from coda.apps.reporting import factcache

#: Every model whose rows (or rows reached through them) shape the fact set.
FACT_MODELS: tuple[type[Model], ...] = (
    FundingRequest,
    FundingRequestReview,
    FundingOrganization,
    Label,
    ExternalFunding,
    Publication,
    PublicationPayment,
    AttachedContract,
    Concept,
    Link,
    Invoice,
    Position,
    FundingAssignment,
    FundingSource,
    Creditor,
    CurrencyConversion,
    Institution,
    Journal,
    Publisher,
    Contract,
    Author,
)


@receiver(post_save)
@receiver(post_delete)
def bump_facts_generation(sender: type[Model], instance: Model, **kwargs: object) -> None:
    """Bump the facts generation on any write to a fact-relevant model.

    Registered for every model, filtering by set membership: the signal
    list is one line per model in FACT_MODELS instead of 36 receiver
    decorators, and a model added to the tuple is covered automatically."""
    if sender in FACT_MODELS:
        factcache.bump_generation()
