"""Business rules for the active-filter summary shown above the filter list.

The summary must tell the user, in the words they recognize, every filter that
is currently narrowing the results — and clicking a chip's remove control must
drop exactly that one value while everything else stays applied.

Rules asserted here:
- the summary lists every active filter, and its count matches the filter badge
- values are shown as names the user recognizes, not raw ids
- dates, years and switches get clarifying wording
- search and sort are toolbar state, not filters — never summarized
- removing one value keeps the remaining filters applied
- with no filters left there is no summary at all
- page size/pagination resets to page 1 after a removal
"""

from datetime import date
from typing import Any, cast

import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.test.html import parse_html
from django.urls import reverse

from coda.apps.contracts.models import Contract
from coda.apps.listfilters import ActiveFilter
from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.domain.color import Color
from coda.domain.contract import PublicationBilling
from tests import modelfactory
from tests.filterdom import selected_values, swap_targets, walk

pytestmark = pytest.mark.django_db


def get_list(client: Client, **params: Any) -> TemplateResponse:
    """GET the funding-request list and return the rendered response."""
    response = client.get(reverse("fundingrequests:list"), data=params)
    assert response.status_code == 200
    return cast(TemplateResponse, response)


def get_list_region(client: Client, **params: Any) -> TemplateResponse:
    """GET just the filtered list region and return the rendered response."""
    response = client.get(reverse("fundingrequests:list_region"), data=params)
    assert response.status_code == 200
    return cast(TemplateResponse, response)


def chip_texts(response: TemplateResponse) -> list[str]:
    """What the filter summary reports to the user, in order."""
    return [chip.text for chip in response.context["active_filters"]]


def chip_for(response: TemplateResponse, text: str) -> ActiveFilter:
    """The summary entry for a value — its remove link is the × the user clicks."""
    return cast(
        ActiveFilter, next(chip for chip in response.context["active_filters"] if chip.text == text)
    )


@pytest.mark.usefixtures("logged_in")
def test__summary__lists_every_active_filter_and_matches_badge(client: Client) -> None:
    """Every selected filter value is summarized, one entry each, matching the badge."""
    response = get_list_region(
        client, processing_status=["approved", "rejected"], payment_status="unpaid"
    )

    assert chip_texts(response) == ["approved", "rejected", "Unpaid"]
    assert response.context["filter_count"] == 3


@pytest.mark.usefixtures("logged_in")
def test__summary__uses_names_users_recognize(client: Client) -> None:
    """Contracts and labels appear by name in the summary — never as raw ids."""
    contract = Contract.objects.create(
        name="DFG Open Access Pauschale",
        start_date=date(2024, 1, 1),
        end_date=date(2027, 12, 31),
        publication_billing=PublicationBilling.Individually.value,
    )
    alpha = label_create("Alpha", Color.from_rgb(255, 0, 0))

    response = get_list_region(
        client,
        contract_name=str(contract.pk),
        labels=str(alpha.pk),
        payment_status="unpaid",
    )

    texts = chip_texts(response)
    assert "DFG Open Access Pauschale" in texts
    assert "Alpha" in texts
    assert "Unpaid" in texts
    assert str(contract.pk) not in texts


@pytest.mark.usefixtures("logged_in")
def test__summary__clarifies_dates_years_and_switches(client: Client) -> None:
    """Bare dates/years/switches get wording that explains what they mean."""
    response = get_list_region(
        client,
        start_date="2025-01-01",
        end_date="2026-12-31",
        contract_year="2025",
        invalid_contract_years="on",
    )

    assert chip_texts(response) == [
        "From 2025-01-01",
        "To 2026-12-31",
        "Year 2025",
        "Invalid years only",
    ]


@pytest.mark.usefixtures("logged_in")
def test__summary__ignores_search_and_sort(client: Client) -> None:
    """Search and sort are toolbar state — neither summarized nor counted as filters."""
    response = get_list_region(client, search_term="quantum", sort_by="date-asc")

    assert chip_texts(response) == []
    assert response.context["filter_count"] == 0


@pytest.mark.usefixtures("logged_in")
def test__summary__reports_publication_type_only_when_narrowed(client: Client) -> None:
    """ "All publications" is the default and is not reported; a narrowed type is."""
    assert chip_texts(get_list_region(client, publication_type="all")) == []

    narrowed = get_list_region(client, publication_type="article")
    assert chip_texts(narrowed) == ["Article"]


@pytest.mark.usefixtures("logged_in")
def test__summary__absent_without_any_filter(client: Client) -> None:
    """Unfiltered browse shows no summary and a zero badge."""
    response = get_list(client)

    assert chip_texts(response) == []
    assert response.context["filter_count"] == 0


@pytest.mark.usefixtures("logged_in")
def test__removing_a_chip__drops_exactly_that_value(client: Client) -> None:
    """Removing one label keeps the other label filter applied."""
    alpha = label_create("Alpha", Color.from_rgb(255, 0, 0))
    beta = label_create("Beta", Color.from_rgb(0, 0, 255))
    label_attach(modelfactory.fundingrequest(title="Alpha paper"), alpha)
    label_attach(modelfactory.fundingrequest(title="Beta paper"), beta)

    response = get_list_region(client, labels=[alpha.pk, beta.pk])
    assert chip_texts(response) == ["Alpha", "Beta"]

    after = client.get(chip_for(response, "Alpha").remove_fragment_url)
    assert after.status_code == 200
    assert chip_texts(cast(TemplateResponse, after)) == ["Beta"]

    # The results are still narrowed by Beta — not unfiltered.
    html = cast(TemplateResponse, after).content.decode()
    assert "Beta paper" in html
    assert "Alpha paper" not in html


@pytest.mark.usefixtures("logged_in")
def test__removing_the_last_chip__ends_with_no_summary(client: Client) -> None:
    """Removing the only filter leaves nothing summarized."""
    response = get_list_region(client, payment_status="unpaid")

    after = client.get(chip_for(response, "Unpaid").remove_fragment_url)
    assert after.status_code == 200
    assert chip_texts(cast(TemplateResponse, after)) == []
    assert cast(TemplateResponse, after).context["filter_count"] == 0


@pytest.mark.usefixtures("logged_in")
def test__removing_a_filter__returns_to_the_first_result_page(client: Client) -> None:
    """A changed filter must not strand the user on a deep page."""
    response = get_list(client, processing_status="approved", page="3")

    after = client.get(chip_for(response, "approved").remove_fragment_url)
    assert after.status_code == 200
    assert cast(TemplateResponse, after).context["page_obj"].number == 1


@pytest.mark.usefixtures("logged_in")
def test__summary__tolerates_stale_references(client: Client) -> None:
    """A deleted contract/label in a saved URL shows its raw value instead of crashing."""
    response = get_list_region(client, contract_name="99999", exclude_labels="99999")

    assert response.status_code == 200
    assert chip_texts(response) == ["99999", "Not: 99999"]


@pytest.mark.usefixtures("logged_in")
def test__list_region__rerenders_the_sidebar_from_the_url(client: Client) -> None:
    """Widget state comes from the server: the fragment re-renders the whole sidebar."""
    response = get_list_region(client, processing_status=["approved", "rejected"])

    dom = parse_html(response.content.decode())
    assert "filter-sidebar-form" in swap_targets(dom)
    assert selected_values(dom, "processing_status") == ["approved", "rejected"]


@pytest.mark.usefixtures("logged_in")
def test__unparsable_contract_year__still_shows_a_removable_year_chip(client: Client) -> None:
    """An ignored year still counts and stays removable, so the user can undo it."""
    response = get_list_region(client, contract_year="abc")

    assert chip_texts(response) == ["Year abc"]
    assert response.context["filter_count"] == 1
    assert "contract_year" not in chip_for(response, "Year abc").remove_fragment_url


def _element_ids(html: str) -> set[str]:
    return {
        element_id
        for element in walk(parse_html(html))
        if (element_id := dict(element.attributes).get("id"))
    }


@pytest.mark.usefixtures("logged_in")
def test__every_chip__points_at_a_control_present_in_the_response(client: Client) -> None:
    """A chip body flashes its control, so the control id it names must exist.

    Renaming a widget (develop converted the publication-state picker to
    ``search-select-multi`` with id ``id_publication_states``) silently breaks
    the flash, because ``filter-chips.js`` resolves the id and returns when the
    element is absent.
    """
    response = get_list_region(
        client,
        processing_status="approved",
        payment_status="unpaid",
        publication_states="Published",
        contract_year="2024",
        exclude_labels="99999",
    )

    ids = _element_ids(response.content.decode())
    assert ids, "region response carried no element ids"
    assert {
        chip.text: chip.source_id
        for chip in response.context["active_filters"]
        if chip.source_id not in ids
    } == {}
