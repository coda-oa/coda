import pytest
from datetime import date
from decimal import Decimal
from io import StringIO

import polars as pl

from coda.apps.exports.services.fundingrequest_csv.export_service import (
    export_fundingrequests_to_csv,
)
from coda.apps.invoices import funding_source_repository
from coda.apps.publications.models import AttachedContract
from coda.contexts.finance.services import invoice_service
from coda.domain.author import InstitutionId
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, PaymentStatus
from coda.domain.finance.invoice_positions import PublicationItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.publication.publication import PublicationId
from tests import domainfactory, modelfactory
from coda.domain.fundingrequest.review import ReviewResult, Review
from coda.domain.money import Money, Currency
from coda.domain.fundingrequest import FundingRequestId
from coda.apps.fundingrequests.repository import save_review


from tests.exports.fundingrequest_csv.helpers import (
    _make_params,
    create_funding_request_with_concepts,
    create_invoice_with_funding_assignments,
    create_invoice_with_publication_position,
)


@pytest.mark.django_db
def test__single_funding_request_with_one_invoice__export_to_csv__returns_csv_with_one_row() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Test Publication for Export")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    position = invoice_positions.create(
        item=PublicationItem(
            PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType("gold-oa"),
        ),
        cost=Money(Decimal("1500.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )
    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[position]
    )
    invoice.id = invoice_service.save(invoice)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(_make_params(period_start, period_end))

    assert isinstance(requests_exports, str)
    assert requests_exports
    assert ";" in requests_exports.splitlines()[0]

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert df.height == 1
    assert df["publication_title"][0] == "Test Publication for Export"
    assert df["invoice_number"][0] == str(invoice.number)
    assert df["invoice_date"][0] == invoice.date.isoformat()
    assert df["request_id"][0] == str(funding_request.request_id)


@pytest.mark.django_db
def test__invoice_comment_with_crlf__export_to_csv__replaces_linebreak_with_single_space() -> None:
    funding_request = modelfactory.fundingrequest(title="CRLF Comment Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    create_invoice_with_publication_position(funding_request, comment="line one\r\nline two")

    requests_exports = export_fundingrequests_to_csv(
        _make_params(date(2026, 1, 1), date(2026, 12, 31))
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert df["invoice_comment"][0] == "line one line two"


@pytest.mark.django_db
def test__review_remarks_with_lf__export_to_csv__replaces_linebreak_with_single_space() -> None:
    funding_request = modelfactory.fundingrequest(title="LF Remarks Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    save_review(
        Review(FundingRequestId(funding_request.id)).update_review(
            ReviewResult.Approved, Money(Decimal("2000.00"), Currency.EUR), "entry one\nentry two"
        )
    )

    requests_exports = export_fundingrequests_to_csv(
        _make_params(date(2026, 1, 1), date(2026, 12, 31))
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert df["review_remarks"][0] == "entry one entry two"


@pytest.mark.django_db
def test__invoice_comment_with_cr__export_to_csv__replaces_cr_with_single_space() -> None:
    funding_request = modelfactory.fundingrequest(title="CR Comment Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    create_invoice_with_publication_position(funding_request, comment="line one\rline two")

    requests_exports = export_fundingrequests_to_csv(
        _make_params(date(2026, 1, 1), date(2026, 12, 31))
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert df["invoice_comment"][0] == "line one line two"


@pytest.mark.django_db
def test__invoice_comment_with_unicode_line_separators__export_to_csv__replaces_them_with_spaces() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Unicode Separator Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    create_invoice_with_publication_position(
        funding_request, comment="line one\u2028line two\u2029line three"
    )

    requests_exports = export_fundingrequests_to_csv(
        _make_params(date(2026, 1, 1), date(2026, 12, 31))
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert df["invoice_comment"][0] == "line one line two line three"
    assert "\u2028" not in requests_exports
    assert "\u2029" not in requests_exports


@pytest.mark.django_db
def test__invoice_comment_with_zero_width_no_break_space__export_to_csv__removes_it() -> None:
    funding_request = modelfactory.fundingrequest(title="ZWNBSP Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    create_invoice_with_publication_position(funding_request, comment="line\ufeffone")

    requests_exports = export_fundingrequests_to_csv(
        _make_params(date(2026, 1, 1), date(2026, 12, 31))
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert df["invoice_comment"][0] == "lineone"
    assert "\ufeff" not in requests_exports


@pytest.mark.django_db
def test__multiline_invoice_comment__export_to_csv__keeps_one_line_per_record() -> None:
    funding_request = modelfactory.fundingrequest(title="Multiline Record Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    create_invoice_with_publication_position(funding_request, comment="line one\r\nline two")

    requests_exports = export_fundingrequests_to_csv(
        _make_params(date(2026, 1, 1), date(2026, 12, 31))
    )

    assert requests_exports.count("\n") == 2
    assert "\r" not in requests_exports


@pytest.mark.django_db
def test__funding_request_with_vocabulary_concepts__export_to_csv__includes_concept_id_columns() -> (
    None
):
    funding_request, subject_area_concept, publication_type_concept = (
        create_funding_request_with_concepts(
            title="Concept Export Publication",
            subject_area_concept_id="DFG-51D",
            publication_type_concept_id="PT-ART",
        )
    )
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    requests_exports = export_fundingrequests_to_csv(
        _make_params(date(2026, 1, 1), date(2026, 12, 31))
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert df.height == 1
    assert df["subject_area_id"][0] == subject_area_concept.concept_id
    assert df["publication_type_id"][0] == publication_type_concept.concept_id
    assert df["subject_area"][0] == subject_area_concept.name
    assert df["publication_type"][0] == publication_type_concept.name


@pytest.mark.django_db
def test__funding_request_without_invoices__export_to_csv__returns_one_row_with_empty_cost_fields() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Publication Only")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(_make_params(period_start, period_end))

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 1

    assert df["publication_title"][0] == "Publication Only"
    assert df["invoice_number"][0] == ""
    assert df["invoice_date"][0] == ""
    assert df["position_amount"][0] == ""
    assert df["funded_amount"][0] == ""


@pytest.mark.django_db
def test__no_funding_requests_in_period__export_to_csv__returns_csv_with_only_header() -> None:
    funding_request_not_in_period = modelfactory.fundingrequest(title="Test Publication for Export")
    funding_request_not_in_period.request_date = date(2025, 5, 1)
    funding_request_not_in_period.save()

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(_make_params(period_start, period_end))

    assert isinstance(requests_exports, str)
    assert requests_exports
    assert ";" in requests_exports.splitlines()[0]

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 0


@pytest.mark.django_db
def test__funding_request_with_invoice_position_with_multiple_funding_assignments__export_to_csv__creates_multiple_rows() -> (
    None
):
    # ARRANGE
    funding_request = modelfactory.fundingrequest(title="Split Cost Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    budget_1 = Budget.new("Budget 1")
    budget_2 = Budget.new("Budget 2")
    budget_1.id = funding_source_repository.create(budget_1)
    budget_2.id = funding_source_repository.create(budget_2)

    position = invoice_positions.create(
        item=PublicationItem(
            PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType("gold-oa"),
        ),
        cost=Money(Decimal("2000.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )
    position.assign_funding(budget_1, Decimal("1200.00"))
    position.assign_funding(budget_2, Decimal("800.00"))

    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[position]
    )
    invoice.id = invoice_service.save(invoice)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(_make_params(period_start, period_end))

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 2

    assert df["publication_title"][0] == "Split Cost Publication"
    assert df["invoice_number"][0] == str(invoice.number)
    assert Decimal(df["funded_amount"][0]) == Decimal("1200.00")
    assert df["funding_source_name"][0] == "Budget 1"

    assert df["publication_title"][1] == "Split Cost Publication"
    assert df["invoice_number"][1] == str(invoice.number)
    assert Decimal(df["funded_amount"][1]) == Decimal("800.00")
    assert df["funding_source_name"][1] == "Budget 2"


@pytest.mark.django_db
def test__funding_request_with_institution_funding_source__export_to_csv__institution_name_is_used() -> (
    None
):
    # ARRANGE
    funding_request = modelfactory.fundingrequest(title="Institution Split Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    institution = modelfactory.institution()
    institution_source = domainfactory.split_source(InstitutionId(institution.pk), institution.name)

    position = invoice_positions.create(
        item=PublicationItem(
            PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType("gold-oa"),
        ),
        cost=Money(Decimal("1000.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )
    position.assign_funding(institution_source, Decimal("1000.00"))

    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[position]
    )
    invoice.id = invoice_service.save(invoice)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(_make_params(period_start, period_end))

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 1
    assert df["funding_source_type"][0] == "institution"
    assert df["funding_source_name"][0] == institution.name


@pytest.mark.django_db
def test__funding_request_with_multiple_invoices__export_to_csv__creates_multiple_rows() -> None:
    # ARRANGE
    funding_request = modelfactory.fundingrequest(title="Multi-Invoice Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    creditor_id = CreditorId(modelfactory.creditor().pk)
    publication_id = PublicationId(funding_request.publication.id)

    position1 = invoice_positions.create(
        item=PublicationItem(publication_id, cost_type=PublicationCostType("gold-oa")),
        cost=Money(Decimal("1000.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )
    invoice1 = domainfactory.invoice(creditor=creditor_id, positions=[position1])
    invoice1.id = invoice_service.save(invoice1)

    position2 = invoice_positions.create(
        item=PublicationItem(publication_id, cost_type=PublicationCostType("gold-oa")),
        cost=Money(Decimal("500.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )
    invoice2 = domainfactory.invoice(creditor=creditor_id, positions=[position2])
    invoice2.id = invoice_service.save(invoice2)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(_make_params(period_start, period_end))

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 2

    assert df["publication_title"][0] == "Multi-Invoice Publication"
    assert df["invoice_number"][0] == str(invoice1.number)

    assert df["publication_title"][1] == "Multi-Invoice Publication"
    assert df["invoice_number"][1] == str(invoice2.number)


@pytest.mark.django_db
def test__funding_request_with_review_result__export_to_csv__includes_review_results_and_labels() -> (
    None
):
    # ARRANGE
    funding_request = modelfactory.fundingrequest(title="Reviewed Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    save_review(
        Review(FundingRequestId(funding_request.id)).update_review(
            ReviewResult.Approved, Money(Decimal("2000.00"), Currency.EUR)
        )
    )

    position = invoice_positions.create(
        item=PublicationItem(
            PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType("gold-oa"),
        ),
        cost=Money(Decimal("1500.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )
    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[position]
    )
    invoice.id = invoice_service.save(invoice)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(_make_params(period_start, period_end))

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 1

    assert df["publication_title"][0] == "Reviewed Publication"
    assert df["review_result"][0] == "approved"


@pytest.mark.django_db
def test__funding_request_with_invoice_filters_funding_source__export_to_csv__returns_filtered_results() -> (
    None
):
    # ARRANGE
    funding_request = modelfactory.fundingrequest(title="Filtered Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    funding_source = domainfactory.budget()
    funding_source.id = funding_source_repository.create(funding_source)

    position = invoice_positions.create(
        item=PublicationItem(
            PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType("gold-oa"),
        ),
        cost=Money(Decimal("1500.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )
    position.assign_funding(funding_source, position.cost.amount)

    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor(name="Test Creditor").pk),
        positions=[position],
    )
    invoice.status = PaymentStatus.Paid
    invoice.id = invoice_service.save(invoice)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(
        _make_params(period_start, period_end, funding_source=funding_source.id)
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 1
    assert df["funding_source_name"][0] == funding_source.name


@pytest.mark.django_db
def test__shared_invoice_filtering_by_funding_source__export_to_csv__only_considers_own_publication_positions() -> (
    None
):
    # ARRANGE
    # Request B finances its own position with source X (passes the criteria filter).
    # The shared invoice carries X only on publication C's position, not on B's or A's.
    funding_request_b = modelfactory.fundingrequest(title="Filter B Own Publication")
    funding_request_b.request_date = date(2026, 5, 1)
    funding_request_b.save()

    funding_request_a = modelfactory.fundingrequest(title="Filter A Unfunded Publication")
    funding_request_a.request_date = date(2026, 5, 1)
    funding_request_a.save()

    funding_request_c = modelfactory.fundingrequest(title="Filter C Shared Publication")
    funding_request_c.request_date = date(2026, 5, 1)
    funding_request_c.save()

    funding_source_x = domainfactory.budget()
    funding_source_x.id = funding_source_repository.create(funding_source_x)
    creditor_id = CreditorId(modelfactory.creditor().pk)

    position_a = domainfactory.publication_position(
        PublicationId(funding_request_a.publication.id), currency=Currency.EUR
    )
    position_c = domainfactory.publication_position(
        PublicationId(funding_request_c.publication.id), currency=Currency.EUR
    )
    position_c.assign_funding(funding_source_x, position_c.cost.amount)
    shared_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[position_a, position_c],
    )
    shared_invoice.id = invoice_service.save(shared_invoice)

    position_b = domainfactory.publication_position(
        PublicationId(funding_request_b.publication.id), currency=Currency.EUR
    )
    position_b.assign_funding(funding_source_x, position_b.cost.amount)
    private_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[position_b],
    )
    private_invoice.id = invoice_service.save(private_invoice)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(
        _make_params(period_start, period_end, funding_source=funding_source_x.id)
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    rows = set(zip(df["publication_title"], df["invoice_number"]))

    # B's own invoice and C's own invoice are exported...
    assert ("Filter B Own Publication", str(private_invoice.number)) in rows
    assert ("Filter C Shared Publication", str(shared_invoice.number)) in rows
    # ...but the shared invoice must not be exported for B just because a
    # foreign publication's position on it carries the filtered funding source.
    assert ("Filter B Own Publication", str(shared_invoice.number)) not in rows
    # A is filtered out entirely: none of its own positions carry source X.
    assert ("Filter A Unfunded Publication", str(shared_invoice.number)) not in rows
    assert df.height == 2


@pytest.mark.django_db
def test__funding_request_with_combined_filters__export_to_csv__returns_correctly_filtered_results() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Filtered Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    save_review(
        Review(FundingRequestId(funding_request.id)).update_review(
            ReviewResult.Approved, Money(Decimal("2000.00"), Currency.EUR)
        )
    )

    budget_1 = Budget.new("Budget 1")
    budget_1.id = funding_source_repository.create(budget_1)
    budget_2 = Budget.new("Budget 2")
    budget_2.id = funding_source_repository.create(budget_2)
    creditor_id = CreditorId(modelfactory.creditor(name="Test Creditor").pk)

    position = invoice_positions.create(
        item=PublicationItem(
            PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType("gold-oa"),
        ),
        cost=Money(Decimal("1500.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )
    position.assign_funding(budget_1, position.cost.amount)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=[position])
    invoice.status = PaymentStatus.Paid
    invoice.id = invoice_service.save(invoice)

    funding_request_rejected = modelfactory.fundingrequest(title="Filtered Publication")
    funding_request_rejected.request_date = date(2026, 5, 1)
    funding_request_rejected.save()

    save_review(
        Review(FundingRequestId(funding_request_rejected.id)).update_review(
            ReviewResult.Rejected, Money(Decimal("2000.00"), Currency.EUR)
        )
    )

    position2 = invoice_positions.create(
        item=PublicationItem(
            PublicationId(funding_request_rejected.publication.id),
            cost_type=PublicationCostType("gold-oa"),
        ),
        cost=Money(Decimal("1500.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )
    position2.assign_funding(budget_2, position2.cost.amount)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=[position2])
    invoice.status = PaymentStatus.Paid
    invoice.id = invoice_service.save(invoice)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(
        _make_params(
            period_start,
            period_end,
            review_results=[ReviewResult.Approved],
            funding_source=budget_1.id,
        )
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 1
    assert df["publication_title"][0] == "Filtered Publication"
    assert df["review_result"][0] == "approved"
    assert df["funding_source_name"][0] == "Budget 1"


@pytest.mark.django_db
def test__funding_request_with_attached_contract_without_invoice__export_to_csv__includes_contract_fields() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Contract Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    contract = modelfactory.contract()
    AttachedContract.objects.create(
        publication=funding_request.publication,
        contract=contract,
        contract_year=2026,
    )

    requests_exports = export_fundingrequests_to_csv(
        _make_params(
            date(2026, 1, 1),
            date(2026, 12, 31),
        )
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert df.height == 1
    assert df["publication_title"][0] == "Contract Publication"
    assert df["contract_name"][0] == contract.name
    assert str(df["contract_year"][0]) == "2026"


@pytest.mark.django_db
def test__funding_request_with_contract_filter__export_to_csv__returns_only_matching_contract() -> (
    None
):
    matching_contract = modelfactory.contract()
    other_contract = modelfactory.contract()

    funding_request_match = modelfactory.fundingrequest(title="Matching Contract Publication")
    funding_request_match.request_date = date(2026, 5, 1)
    funding_request_match.save()
    AttachedContract.objects.create(
        publication=funding_request_match.publication,
        contract=matching_contract,
        contract_year=2026,
    )

    funding_request_other = modelfactory.fundingrequest(title="Other Contract Publication")
    funding_request_other.request_date = date(2026, 5, 1)
    funding_request_other.save()
    AttachedContract.objects.create(
        publication=funding_request_other.publication,
        contract=other_contract,
        contract_year=2026,
    )

    requests_exports = export_fundingrequests_to_csv(
        _make_params(
            date(2026, 1, 1),
            date(2026, 12, 31),
            contract_id=matching_contract.id,
        )
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert df.height == 1
    assert df["publication_title"][0] == "Matching Contract Publication"
    assert df["contract_name"][0] == matching_contract.name


@pytest.mark.django_db
def test__shared_invoice_across_multiple_publications__export_to_csv__does_not_duplicate_rows() -> (
    None
):
    creditor_id = CreditorId(modelfactory.creditor().pk)

    titles = [
        "Shared Invoice Pub 1",
        "Shared Invoice Pub 2",
        "Shared Invoice Pub 3",
        "Shared Invoice Pub 4",
    ]

    positions = []
    for idx, title in enumerate(titles, start=1):
        fr = modelfactory.fundingrequest(title=title)
        fr.request_date = date(2025, 2, idx)
        fr.save()

        position = domainfactory.publication_position(
            PublicationId(fr.publication.id), currency=Currency.EUR
        )
        positions.append(position)

    shared_invoice = domainfactory.invoice(creditor=creditor_id, positions=positions)
    shared_invoice.id = invoice_service.save(shared_invoice)

    requests_exports = export_fundingrequests_to_csv(
        _make_params(
            date(2025, 1, 1),
            date(2025, 12, 31),
        )
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    shared_invoice_rows = df.filter(pl.col("invoice_number") == str(shared_invoice.number))

    assert shared_invoice_rows.height == 4


@pytest.mark.django_db
def test__funding_request_with_comma_decimal_separator__export_to_csv__formats_money_values_with_comma() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Comma Separator Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    create_invoice_with_funding_assignments(
        funding_request,
        cost_amount=Decimal("1600.00"),
        budget_amount=Decimal("1200.00"),
        institution_amount=Decimal("400.00"),
    )

    requests_exports = export_fundingrequests_to_csv(
        _make_params(date(2026, 1, 1), date(2026, 12, 31), decimal_separator=",")
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert sorted(df["position_amount"].to_list()) == ["1600,0000", "1600,0000"]
    assert sorted(df["funded_amount"].to_list()) == ["1200,0000", "400,0000"]
    assert sorted(df["tax_rate"].to_list()) == ["19,0000", "19,0000"]


@pytest.mark.django_db
def test__funding_request_with_estimated_cost_and_review__comma_separator__formats_remaining_money_columns_with_comma() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="All Money Columns Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.estimated_cost = Decimal("2500.00")
    funding_request.estimated_cost_currency = "EUR"
    funding_request.save()

    save_review(
        Review(FundingRequestId(funding_request.id)).update_review(
            ReviewResult.Approved, Money(Decimal("2000.00"), Currency.EUR), "remarks"
        )
    )

    create_invoice_with_funding_assignments(funding_request)

    requests_exports = export_fundingrequests_to_csv(
        _make_params(date(2026, 1, 1), date(2026, 12, 31), decimal_separator=",")
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert sorted(set(df["estimated_amount"].to_list())) == ["2500,0000"]
    assert sorted(set(df["decided_funding_amount"].to_list())) == ["2000,0000"]


@pytest.mark.django_db
def test__funding_request__export_to_csv__keeps_dot_decimal_separator_by_default() -> None:
    funding_request = modelfactory.fundingrequest(title="Dot Separator Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    create_invoice_with_funding_assignments(funding_request)

    requests_exports = export_fundingrequests_to_csv(
        _make_params(date(2026, 1, 1), date(2026, 12, 31))
    )

    assert "1500.0000" in requests_exports
    assert "1500,0000" not in requests_exports
