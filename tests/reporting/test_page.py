import hashlib
import re
from decimal import Decimal
from http import HTTPStatus
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.staticfiles.finders import find
from django.test import Client
from django.test.html import parse_html
from django.urls import reverse
from django.utils import timezone

from coda.apps.fundingrequests.forms import (
    _FACET_CHOICE_LIMIT,
    FundingRequestListFilterForm,
)
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.models import Invoice
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models import PublicationAttachedConcept
from coda.apps.reporting.drilldown import facet_param_names
from coda.apps.reporting.views.page import (
    DIMENSION_GROUPS,
    DimensionRow,
    DimensionSection,
    MeasureColumn,
)
from coda.contexts.statistics import charts
from coda.contexts.statistics.dimensions import DIMENSIONS
from coda.contexts.statistics.dto import Measure
from coda.domain.money import Currency
from coda.domain.publication import License, OpenAccessType
from tests import modelfactory
from tests.filterdom import _attrs, walk
from tests.reporting import helpers

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

PERIOD = {"start_date": "2026-01-01", "end_date": "2026-12-31"}


def seed() -> SimpleNamespace:
    """One fully funded request, one without an invoice, one without a rate.

    The funded request touches every dimension of the §7 registry; the other
    two drive the headline's provenance counters (ADR-0003).
    """
    institution = modelfactory.institution()
    funded = helpers.request("Funded paper")
    helpers.corresponding_author(funded, institution.pk)
    _subject_area_from_configured_vocabulary(funded)
    _named_publication_type(funded)
    publication = funded.publication
    publication.license = License.CC_BY.name
    publication.open_access_type = OpenAccessType.Gold.name
    publication.save()
    helpers.with_attached_contract(funded)
    position = helpers.position(publication.pk, Decimal("1000.00"), Decimal("0.20"))
    source = helpers.budget("Central Fund")
    position.assign_funding(source, Decimal("600.00"))
    helpers.invoice([position])

    # The publication factory randomizes license/open-access type; pin the
    # licenses so the license round-trip below is deterministic.
    without_invoice = helpers.request("Paper without invoice")
    without_invoice.publication.license = License.CC0.name
    without_invoice.publication.save()
    unconvertible = helpers.request("Paper without rate")
    unconvertible.publication.license = License.CC_BY_NC_SA.name
    unconvertible.publication.save()
    foreign = helpers.position(
        unconvertible.publication.pk,
        Decimal("500.00"),
        Decimal("0.19"),
        currency=Currency.USD,
    )
    unconvertible_invoice = helpers.invoice([foreign])

    journal = publication.article_journal
    assert journal is not None
    attached = publication.attached_contracts.get()
    return SimpleNamespace(
        funded=funded,
        publication=publication,
        journal=journal,
        publisher=journal.publisher,
        institution=institution,
        source=source,
        contract=attached.contract,
        contract_year=attached.contract_year,
        funder=funded.external_funding.get().organization,
        subject_area=publication.subject_area,
        publication_type=publication.publication_type,
        unconvertible_invoice=unconvertible_invoice,
    )


def _subject_area_from_configured_vocabulary(funded: FundingRequest) -> None:
    """Attach a subject-area concept from the vocabulary the facet offers —
    only those are expressible as list filters, hence only those get links."""
    GlobalPreferences.get_subject_classification_vocabulary()  # ensures the default is set
    vocabulary = GlobalPreferences.objects.get().subject_classification_vocabulary
    assert vocabulary is not None
    concept = modelfactory.concept(vocabulary=vocabulary)
    funded.publication.subject_area = PublicationAttachedConcept.objects.create(
        name=concept.name, vocabulary=concept.vocabulary, entity_id=concept.entity_id
    )
    funded.publication.save()


def _named_publication_type(funded: FundingRequest) -> None:
    """Attach a publication-type concept from the vocabulary the facet offers —
    only those are expressible as list filters, hence only those get links."""
    GlobalPreferences.get_article_publication_type_vocabulary()  # ensures the default is set
    vocabulary = GlobalPreferences.objects.get().article_publication_type_vocabulary
    assert vocabulary is not None
    concept = modelfactory.concept(vocabulary=vocabulary)
    funded.publication.publication_type = PublicationAttachedConcept.objects.create(
        name=concept.name, vocabulary=vocabulary, entity_id=concept.entity_id
    )
    funded.publication.save()


def goto(client: Client, **query: str) -> "_MonkeyPatchedWSGIResponse":
    return client.get(reverse("reporting:stats_fundingrequests"), data={**PERIOD, **query})


def sections_of(response: "_MonkeyPatchedWSGIResponse") -> dict[str, DimensionSection]:
    """The sections the response actually renders: those of its active tab."""
    return {
        section.dimension_id: section
        for entry in response.context["groups"]
        for section in entry["sections"]
    }


def sections_by_id(client: Client, **query: str) -> dict[str, DimensionSection]:
    """Every dimension's section, gathered from the tab that renders it.
    The page shows one tab's sections at a time, so a cross-tab view takes
    one request per tab."""
    merged: dict[str, DimensionSection] = {}
    for tab in ("publication", "venues", "cost", "attribution"):
        merged |= sections_of(goto(client, tab=tab, **query))
    return merged


def row_by_label(section: DimensionSection, label: str) -> DimensionRow:
    return next(row for row in section.rows if row.label == label)


def column(section: DimensionSection, measure: Measure) -> MeasureColumn:
    return next(col for col in section.columns if col.measure is measure)


def query_params(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def funded_journal_pk() -> int:
    from coda.apps.publications.models import Publication

    return cast(int, Publication.objects.get(title="Funded paper").article_journal_id)


@pytest.mark.django_db
def test__reporting_page__anonymous__redirects_to_login(client: Client) -> None:
    response = client.get(reverse("reporting:stats_fundingrequests"))

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"].startswith(reverse("login"))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__bare_get__redirects_to_current_year_period(client: Client) -> None:
    year = timezone.localdate().year

    response = client.get(reverse("reporting:stats_fundingrequests"))

    assert response.status_code == HTTPStatus.FOUND
    assert query_params(response.headers["Location"]) == {
        "start_date": [f"{year}-01-01"],
        "end_date": [f"{year}-12-31"],
    }


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__bare_get_with_filters__redirect_preserves_them(client: Client) -> None:
    year = timezone.localdate().year

    response = client.get(
        reverse("reporting:stats_fundingrequests"), data={"license": License.CC_BY.value}
    )

    assert response.status_code == HTTPStatus.FOUND
    assert query_params(response.headers["Location"]) == {
        "license": [License.CC_BY.value],
        "start_date": [f"{year}-01-01"],
        "end_date": [f"{year}-12-31"],
    }


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__explicit_period__renders(client: Client) -> None:
    seed()

    response = goto(client)

    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__renders_a_section_per_registered_dimension(client: Client) -> None:
    seed()

    assert set(sections_by_id(client)) == {dimension.id for dimension in DIMENSIONS}


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__every_chart_renders_a_plotly_mount_and_json_script(
    client: Client,
) -> None:
    """Every registered dimension pairs its one combined figure with one
    mount and one json_script payload; the tabs show one group at a time, so
    the union over the group tabs covers every dimension, and the treemap
    (Attribution) and the timeline (Overview) add their mounts."""
    seed()

    group_ids = [group.id for group in DIMENSION_GROUPS]
    mounted: set[str] = set()
    script_ids: set[str] = set()
    for tab in group_ids:
        html = goto(client, tab=tab).content.decode()
        dom = parse_html(html)
        for element in walk(dom):
            attrs = dict(element.attributes)
            if element.name == "div" and attrs.get("data-chart"):
                mounted.add(str(attrs["data-chart"]))
            if element.name == "script" and attrs.get("type") == "application/json":
                script_ids.add(str(attrs.get("id", "")))

    expected = {f"chart-{dimension.id}" for dimension in DIMENSIONS}
    expected.add("chart-institution-treemap")
    assert mounted == expected
    assert mounted <= script_ids


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__headline__counts_publications_spend_and_provenance(
    client: Client,
) -> None:
    seed()

    headline = goto(client).context["headline"]

    assert headline.publications == 3
    assert headline.spend == Decimal("1200.00")
    assert headline.requests_without_invoice == 1
    assert headline.requests_unconvertible == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__currency_incomplete_notice__counts_requests_and_links_invoices(
    client: Client,
) -> None:
    """The page states how many requests lost amounts and links each one's
    invoices (plan §9, §10 Q21)."""
    fixture = seed()

    response = goto(client)

    number = Invoice.objects.get(pk=fixture.unconvertible_invoice).number
    assert [(i.pk, i.number) for i in response.context["incomplete_invoices"]] == [
        (fixture.unconvertible_invoice, number)
    ]

    html = " ".join(response.content.decode().split())
    assert reverse("invoices:detail", args=[fixture.unconvertible_invoice]) in html
    assert number in html
    assert "1 request with excluded amounts" in html
    # The KPI card lives on the overview tab; the notice renders on both.
    overview_html = " ".join(
        client.get(
            reverse("reporting:stats_fundingrequests"),
            data={**PERIOD, "tab": "overview"},
        )
        .content.decode()
        .split()
    )
    assert "Requests with excluded amounts" in overview_html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__paid_out_nothing__renders_dash_not_zero(client: Client) -> None:
    """A funded value that has paid out nothing keeps its row (the count is
    real) but shows "—" in the spend column — zero-money rows are noise."""
    seed()

    html = goto(client, tab="attribution").content.decode()

    institution = re.search(r'id="statistics-institution"[\s\S]*?</table>', html)
    assert institution is not None
    assert "—" in institution.group(0)
    assert re.search(r">\s*0\.00\s*€", institution.group(0)) is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__additive_dimension__shows_total(client: Client) -> None:
    seed()


    value_column = column(sections_by_id(client)["subject_area"], Measure.PAID_OUT)
    assert value_column.note is None
    assert value_column.total == Decimal("1200.00")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__non_additive_dimension__shows_note_instead_of_total(
    client: Client,
) -> None:
    seed()

    value_column = column(sections_by_id(client)["institution"], Measure.PUBLICATIONS)
    assert value_column.total is None
    assert value_column.note is not None
    assert "double-counted" in value_column.note


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__chart_rows__link_to_the_reporting_region(
    client: Client,
) -> None:
    """§2 #7: clicking a row filters the statistics page itself — the link
    carries the row's facet value plus the active filters, and a value already
    among them toggles off."""
    fixture = seed()

    sections = sections_by_id(client)
    region_url = reverse("reporting:stats_fundingrequests_region")

    expected: dict[str, tuple[DimensionSection, str, str, str]] = {
        "journal": (
            sections["journal"],
            fixture.journal.title,
            "journal",
            str(fixture.journal.pk),
        ),
        "publisher": (
            sections["publisher"],
            fixture.publisher.name,
            "publisher",
            str(fixture.publisher.pk),
        ),
        "institution": (
            sections["institution"],
            fixture.institution.name,
            "institution",
            str(fixture.institution.pk),
        ),
        "funder": (
            sections["funder"],
            fixture.funder.name,
            "funder",
            str(fixture.funder.pk),
        ),
        "subject_area": (
            sections["subject_area"],
            fixture.subject_area.name,
            "subject_area",
            str(fixture.subject_area.entity_id),
        ),
        "publication_type": (
            sections["publication_type"],
            fixture.publication_type.name,
            "publication_type_concept",
            str(fixture.publication_type.entity_id),
        ),
        "license": (
            sections["license"],
            License.CC_BY.name,
            "license",
            License.CC_BY.value,
        ),
        "open_access_type": (
            sections["open_access_type"],
            OpenAccessType.Gold.name,
            "open_access_type",
            OpenAccessType.Gold.value,
        ),
        "publication_form": (
            sections["publication_form"],
            "article",
            "publication_form",
            "article",
        ),
        "cost_type": (sections["cost_type"], "gold-oa", "cost_type", "gold-oa"),
        "funding_source": (
            sections["funding_source"],
            "Central Fund",
            "funding_source",
            str(fixture.source.id),
        ),
    }
    for dimension_id, (section, label, param, value) in expected.items():
        row = row_by_label(section, label)
        assert row.link is not None, dimension_id
        assert row.link.startswith(region_url), dimension_id
        params = query_params(row.link)
        assert params[param] == [value], dimension_id
        assert params["start_date"] == ["2026-01-01"], dimension_id
        assert params["end_date"] == ["2026-12-31"], dimension_id

    contract_row = row_by_label(
        sections["contract"], f"{fixture.contract.name} ({fixture.contract_year})"
    )
    assert contract_row.link is not None
    contract_params = query_params(contract_row.link)
    assert contract_params["contract_name"] == [str(fixture.contract.pk)]
    assert contract_params["contract_year"] == [str(fixture.contract_year)]

    # Toggle: filtering by the journal again removes it from the params.
    journal_row = row_by_label(
        sections_by_id(client, journal=str(fixture.journal.pk))["journal"], fixture.journal.title
    )
    assert journal_row.link is not None
    assert "journal" not in query_params(journal_row.link)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__offers_one_link_into_the_request_list(
    client: Client,
) -> None:
    """The page's bridge into the data: one link by the headline carrying the
    page's whole filter set — not one per chart row."""
    seed()

    response = goto(client, license=License.CC_BY.value)
    assert response.context["list_view_url"].startswith(reverse("fundingrequests:list"))
    list_params = query_params(response.context["list_view_url"])
    assert list_params["license"] == [License.CC_BY.value]
    assert list_params["start_date"] == ["2026-01-01"]
    list_view_url_value = response.context["list_view_url"]

    html = parse_html(response.content.decode())
    list_links = [
        el for el in walk(html) if el.name == "a" and _attrs(el).get("href") == list_view_url_value
    ]
    assert len(list_links) == 1
    assert _attrs(list_links[0]).get("title") == (
        "Show these funding requests in the list, with the active filters"
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__unassigned_and_unknown_rows__have_no_drill_down(
    client: Client,
) -> None:
    seed()

    sections = sections_by_id(client)

    unassigned = row_by_label(sections["funding_source"], "Unassigned")
    assert unassigned.link is None
    unknown = row_by_label(sections["institution"], "Unknown")
    assert unknown.link is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__publication_without_journal_or_publisher__forms_unknown_row_without_facet(
    client: Client,
) -> None:
    """§2 #7: the "Unknown" form row has no facet value behind it —
    ``PublicationFormCriteria`` matches neither form — so it carries no
    drill-down, and the article/monograph facets both exclude the request."""
    seed()
    formless = helpers.request("Formless paper")
    formless.publication.article_journal = None
    formless.publication.save()

    section = sections_by_id(client)["publication_form"]
    assert [(row.label, row.publications) for row in section.rows] == [
        ("article", 3),
        ("Unknown", 1),
    ]
    # The Unknown row is the unattributed sentinel: the section header counts
    # the requests the facet cannot express as a value.
    assert section.unattributed == 1
    assert row_by_label(section, "Unknown").link is None

    articles = client.get(
        reverse("fundingrequests:list"), {**PERIOD, "publication_form": "article"}
    )
    titles = {str(item.publication_title) for item in articles.context["entities"]}
    assert titles == {"Funded paper", "Paper without invoice", "Paper without rate"}

    monographs = client.get(
        reverse("fundingrequests:list"), {**PERIOD, "publication_form": "monograph"}
    )
    assert list(monographs.context["entities"]) == []


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__active_filters__narrow_every_chart_and_survive_in_row_links(
    client: Client,
) -> None:
    seed()

    sections = sections_by_id(client, license=License.CC_BY.value)

    # Only the CC-BY request remains, so the additive totals reflect exactly it.
    assert column(sections["subject_area"], Measure.PAID_OUT).total == Decimal("1200.00")
    assert sections["journal"].rows[0].publications == 1

    journal_link = sections["journal"].rows[0].link
    assert journal_link is not None
    link_params = query_params(journal_link)
    assert link_params["license"] == [License.CC_BY.value]
    assert link_params["journal"] == [str(funded_journal_pk())]
    assert journal_link.startswith(reverse("reporting:stats_fundingrequests_region"))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__row_links__reproduce_their_chart_sets_in_the_region(
    client: Client,
) -> None:
    """Round-trip (§2 #7, plan §11): loading a row's link as the statistics
    region yields exactly the requests the chart row counted, per facet."""
    fixture = seed()
    sections = sections_by_id(client)

    cases: dict[str, tuple[DimensionSection, str, str, str]] = {
        "institution": (
            sections["institution"],
            fixture.institution.name,
            "institution",
            str(fixture.institution.pk),
        ),
        "license": (
            sections["license"],
            License.CC_BY.name,
            "license",
            License.CC_BY.value,
        ),
        "journal": (
            sections["journal"],
            fixture.journal.title,
            "journal",
            str(fixture.journal.pk),
        ),
        "publisher": (
            sections["publisher"],
            fixture.publisher.name,
            "publisher",
            str(fixture.publisher.pk),
        ),
        "funding_source": (
            sections["funding_source"],
            "Central Fund",
            "funding_source",
            str(fixture.source.id),
        ),
    }

    for dimension_id, (section, label, param, value) in cases.items():
        link = row_by_label(section, label).link
        assert link is not None, dimension_id
        assert query_params(link)[param] == [value], dimension_id

        region_response = client.get(link, headers={"hx-request": "true"})

        assert region_response.status_code == HTTPStatus.OK, dimension_id
        # The filtered region's own section counts exactly the row's set —
        # but a partition dimension (funding_source) legitimately keeps the
        # "Unassigned" remainder row of the same requests.
        section_rows = sections_of(region_response)[dimension_id].rows
        labels = [row.label for row in section_rows if not row.is_other]
        if dimension_id == "funding_source":
            assert labels == ["Central Fund", "Unassigned"], dimension_id
        else:
            assert labels == [label], dimension_id


@pytest.mark.usefixtures("logged_in")
@pytest.mark.django_db
def test__reporting_page__every_dimension__section_measures_and_facet_round_out_the_registry(
    client: Client,
) -> None:
    """§7 completeness: every registry dimension gets its section with one
    combined figure and table columns for every supported measure — the total
    for additive measures and the double-counting note otherwise — and every
    dimension has a facet whose params the shared form actually accepts (§2 #7)."""
    seed()
    form_fields = set(FundingRequestListFilterForm().fields)
    sections = sections_by_id(client)

    for dimension in DIMENSIONS:
        assert dimension.id in sections, dimension.id
        section = sections[dimension.id]
        assert section.label == dimension.label, dimension.id

        assert section.chart.data_id == f"chart-{dimension.id}", dimension.id
        # The double-counting prohibitions (plan §7: no publication count by
        # cost type) live here: value columns are driven strictly by the
        # registry's measures, never by the grouping's internal per-value
        # counts.
        assert {col.measure for col in section.columns} == set(dimension.measures()), (
            dimension.id,
        )
        for measure in dimension.measures():
            value_column = column(section, measure)
            assert value_column.label == charts.MEASURE_LABELS[measure], (
                dimension.id,
                measure,
            )
            if dimension.is_additive(measure):
                assert value_column.total is not None, (dimension.id, measure)
                assert value_column.note is None, (dimension.id, measure)
            else:
                assert value_column.total is None, (dimension.id, measure)
                assert value_column.note == charts.NON_ADDITIVE_NOTE, (dimension.id, measure)

        facet_params = facet_param_names(dimension.id)
        assert facet_params, dimension.id
        assert set(facet_params) <= form_fields, dimension.id


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_region__swaps_sidebar_toolbar_count_and_sections(
    client: Client,
) -> None:
    seed()

    response = client.get(
        reverse("reporting:stats_fundingrequests_region"),
        data={**PERIOD, "tab": "publication"},
        headers={"hx-request": "true"},
    )

    html = response.content.decode()
    assert 'hx-swap-oob="innerHTML:#filter-sidebar-form"' in html
    assert 'data-chart="chart-subject_area"' in html
    assert response["HX-Push-Url"].startswith(reverse("reporting:stats_fundingrequests"))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__plotly_asset__matches_the_installed_plotly_bundle() -> None:
    path = find("js/vendor/plotly.min.js")
    assert path is not None

    import plotly.offline

    with open(path, "rb") as asset:
        vendored = hashlib.sha256(asset.read()).hexdigest()
    bundled = hashlib.sha256(plotly.offline.get_plotlyjs().encode("utf-8")).hexdigest()
    assert vendored == bundled


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__nav__entry_links_to_statistics(client: Client) -> None:
    html = client.get(reverse("home")).content.decode()

    assert reverse("reporting:stats_fundingrequests") in html
    assert "Statistics" in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_home__offers_a_statistics_card(client: Client) -> None:
    html = client.get(reverse("reporting:home")).content.decode()

    assert reverse("reporting:stats_fundingrequests") in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__facet_chips__name_values_and_point_back_at_the_page(
    client: Client,
) -> None:
    """The shared rail works here too: the statistics-era facets get named,
    removable chips on the statistics page, pointing back at this page."""
    fixture = seed()

    response = goto(client, journal=str(fixture.journal.pk), publication_form="monograph")

    chips = response.context["active_filters"]
    assert [chip.text for chip in chips] == [
        "Monograph",
        "From 2026-01-01",
        "To 2026-12-31",
        fixture.journal.title,
    ]
    assert response.context["filter_count"] == 4
    assert all(
        chip.remove_url.startswith(reverse("reporting:stats_fundingrequests")) for chip in chips
    )


@pytest.mark.django_db
def test__statistics_urls__resolve() -> None:
    assert reverse("reporting:stats_fundingrequests") == "/reporting/stats/fundingrequests/"
    assert (
        reverse("reporting:stats_fundingrequests_region")
        == "/reporting/stats/fundingrequests/region/"
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__compare_with_one_sided_range__renders_no_comparison(
    client: Client,
) -> None:
    """A one-sided range has a defined start but an undefined prior window —
    the prior period is undefined, not zero. The compare toggle must render
    no comparison at all: no deltas, no zero-filled previous series."""
    seed()

    response = goto(client, compare="1", end_date="")
    headline = response.context["headline"]
    assert headline.delta_publications is None
    assert headline.delta_spend is None
    assert response.context["compare"] is False
    assert response.context["comparison"] is None
    assert "headline-delta" not in response.content.decode()

    # With both bounds the same toggle compares for real.
    compared = goto(client, compare="1")
    assert compared.context["compare"] is True
    assert compared.context["comparison"] is not None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__list_link__carries_no_statistics_state(client: Client) -> None:
    """The bridge into the funding-request list carries the page's filters,
    never its own display state (tab, compare, resolution)."""
    seed()

    url = goto(client, compare="1", resolution="monthly", tab="venues").context["list_view_url"]

    from urllib.parse import parse_qs, urlparse

    params = parse_qs(urlparse(url).query)
    assert "tab" not in params
    assert "compare" not in params
    assert "resolution" not in params


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__registry_size_journal_table__renders_capped_rail(
    client: Client,
) -> None:
    """Real installations have tens of thousands of journals and publishers;
    enumerating them all as rail <option>s OOM-killed the container on the
    first page load. Each capped facet must render at most the cap, with the
    hidden search inputs the server-side narrowing round-trips through."""
    publisher = modelfactory.publisher(name="Shared publisher")
    for index in range(_FACET_CHOICE_LIMIT + 150):
        modelfactory.journal(publisher_id=publisher.pk, title=f"Journal {index:04d}")

    response = goto(client)

    assert response.status_code == HTTPStatus.OK
    html = response.content.decode()
    for facet in ("journal", "publisher"):
        widget = re.search(
            rf'<search-select-multi id="id_{facet}"[\s\S]*?</search-select-multi>', html
        )
        assert widget is not None, facet
        assert widget.group(0).count("<option") <= _FACET_CHOICE_LIMIT, facet
        assert f'name="{facet}_q"' in widget.group(0), facet
