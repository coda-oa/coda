"""The funding-request filter rail's chip assembly.

One removable chip per active filter value, in the rail's group order. This
is the fundingrequests half of the rail: the form owns the fields and
choices, this module owns how the active ones show as chips. The genuinely
shared machinery (ChipBuilder, URL helpers, the region mixin) lives in
``coda.apps.listfilters``; invoices builds its own summary beside its form
from the same builder.
"""

import uuid
from collections.abc import Sequence

from django.db.models import Model
from django.http import HttpRequest

from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.forms import (
    cost_type_choices,
    license_choices,
    payment_status_choices,
    publication_state_choices,
)
from coda.apps.fundingrequests.models import FundingOrganization, Label
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import FundingSource
from coda.apps.journals.models import Journal
from coda.apps.listfilters import ChipBuilder, FilterSummary
from coda.apps.publications.models import PublicationAttachedConcept
from coda.apps.publishers.models import Publisher
from coda.domain.date import DateRange

_DATE_START_KEY = "start_date"
_DATE_END_KEY = "end_date"
_DEFAULT_PUBLICATION_TYPE = "all"


def _names_by_pk(model: type[Model], values: Sequence[str]) -> dict[str, str]:
    """pk -> display name for the selected values; unparseable ones (stale
    URLs) stay unresolved and the chip falls back to the raw value. The
    label field is the model's own facet_label_field."""
    pks = [value for value in values if value.isdigit()]
    if not pks:
        return {}
    label_field = getattr(model, "facet_label_field", "name")
    return {
        str(pk): name
        for pk, name in model.objects.filter(pk__in=pks).values_list("pk", label_field)
    }


def _concept_names(values: Sequence[str]) -> dict[str, str]:
    """entity_id -> name for the selected concepts - both concept-typed facets
    filter ``PublicationAttachedConcept`` rows by ``entity_id``."""
    ids = []
    for value in values:
        try:
            ids.append(uuid.UUID(value))
        except ValueError:
            continue
    if not ids:
        return {}
    return {
        str(entity_id): name
        for entity_id, name in PublicationAttachedConcept.objects.filter(
            entity_id__in=ids
        ).values_list("entity_id", "name")
    }


def build_filter_summary(
    request: HttpRequest,
    labels: Sequence[Label],
    contracts: Sequence[Contract],
    *,
    list_url_name: str,
    region_url_name: str,
    included: set[int],
    excluded: set[int],
    date_range: DateRange | None,
    date_range_error: str | None,
) -> FilterSummary:
    """One removable chip per active filter value, in the rail's group order.

    The remove links point at ``list_url_name``/``region_url_name``, so a
    page reusing the rail (e.g. the statistics page) builds chips that point
    at itself.

    Text is the bare value except where that would be ambiguous (dates,
    contract year, excluded labels, switch). A deleted Contract falls back to
    its raw id; label chips come from the resolved include/exclude sets, so
    ids the form dropped never appear.
    """
    chips = ChipBuilder(
        request,
        list_url_name=list_url_name,
        region_url_name=region_url_name,
    )
    chips.multi("processing_status")
    chips.multi("payment_status", labels=dict(payment_status_choices))
    chips.multi("payment_methods")
    chips.multi("open_access_type")

    publication_type = request.GET.get("publication_type")
    if publication_type and publication_type != _DEFAULT_PUBLICATION_TYPE:
        chips.add("publication_type", publication_type, publication_type.title())

    chips.multi("publication_states", labels=dict(publication_state_choices))
    chips.date_range(
        start_key=_DATE_START_KEY,
        end_key=_DATE_END_KEY,
        start_source_id="id_start_date",
        end_source_id="id_end_date",
        date_range=date_range,
        error=date_range_error,
    )

    subject_values = request.GET.getlist("subject_area")
    concept_values = request.GET.getlist("publication_type_concept")
    concept_names = _concept_names(subject_values + concept_values)
    chips.multi("subject_area", labels=concept_names)
    chips.multi("publication_type_concept", labels=concept_names)
    chips.multi("license", labels=dict(license_choices))
    chips.multi(
        "institution",
        labels=_names_by_pk(Institution, request.GET.getlist("institution")),
    )
    chips.multi(
        "journal",
        labels=_names_by_pk(Journal, request.GET.getlist("journal")),
    )
    chips.multi("publisher", labels=_names_by_pk(Publisher, request.GET.getlist("publisher")))
    chips.multi("funder", labels=_names_by_pk(FundingOrganization, request.GET.getlist("funder")))
    chips.multi(
        "funding_source",
        labels=_names_by_pk(FundingSource, request.GET.getlist("funding_source")),
    )
    chips.multi("cost_type", labels=dict(cost_type_choices))

    chips.single(
        "contract_name",
        labels={str(contract.pk): contract.name for contract in contracts},
    )
    chips.single("contract_year", prefix="Year ")
    chips.switch("invalid_contract_years", "Invalid years only")

    names = {label.pk: label.name for label in labels}
    colors = {label.pk: label.hexcolor for label in labels}

    def label_chips(param: str, ids: set[int], prefix: str = "") -> None:
        for value in sorted(ids):
            chips.add(
                param, str(value), prefix + names[value], kind="label", label_color=colors[value]
            )

    label_chips("labels", included)
    label_chips("exclude_labels", excluded, "Not: ")
    return chips.summary()
