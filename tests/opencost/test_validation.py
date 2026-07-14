from datetime import date
from decimal import Decimal

import pytest

from coda.apps.opencost.models import OpenCostReport
from coda.apps.opencost.report_service import generate_report
from coda.apps.opencost.validation import validate_report
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models._links import LinkType, Link

from tests import modelfactory
from tests.opencost.helpers import (
    create_contract_with_identifiers,
    create_publication_with_invoice,
    create_institution_with_identifiers,
    create_creditor,
    create_invoice,
    create_position,
)


@pytest.mark.django_db
def test_validate_report_empty_report() -> None:
    """Verify validation returns empty list for report with no data."""
    report = OpenCostReport.objects.create(
        title="Empty Report",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
    )

    warnings = validate_report(report)

    assert warnings == []
    assert report.has_issues() is False
    assert report.get_issue_counts() == {"errors": 0, "warnings": 0}


@pytest.mark.django_db
def test_validate_report_contract_missing_esac_id() -> None:

    contract = modelfactory.contract()
    contract.name = "Contract Without ESAC"
    contract.start_date = date(2024, 1, 1)
    contract.end_date = date(2024, 12, 31)
    contract.save()

    creditor = create_creditor(name="Test Creditor")
    invoice = create_invoice(
        creditor=creditor,
        invoice_date=date(2024, 6, 1),
        number="INV-TEST-001",
    )
    create_position(
        invoice=invoice,
        contract=contract,
        cost_amount=Decimal("1000.00"),
        cost_type="read",
    )

    report = generate_report(
        title="Test Report",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
    )

    warnings = validate_report(report)

    esac_errors = [w for w in warnings if "ESAC ID" in w.message]
    assert len(esac_errors) > 0
    assert esac_errors[0].level == "error"
    assert esac_errors[0].entity_type == "contract"


@pytest.mark.django_db
def test_validate_report_publication_missing_doi() -> None:

    fr = modelfactory.fundingrequest(title="Publication Without DOI")
    fr.publication.links.filter(type__name="DOI").delete()

    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-PUB-001",
        cost_amount=Decimal("1500.00"),
    )

    report = generate_report(
        title="Test Report",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
    )

    warnings = validate_report(report)

    doi_warnings = [w for w in warnings if "DOI" in w.message]
    assert len(doi_warnings) > 0
    assert doi_warnings[0].level == "warning"
    assert doi_warnings[0].entity_type == "publication"


@pytest.mark.django_db
def test_validation_caching_consistency() -> None:
    # Create report with some data
    # Note: No invoices, so report will be empty, but we're testing caching behavior
    contract = modelfactory.contract()
    contract.start_date = date(2024, 1, 1)
    contract.end_date = date(2024, 12, 31)
    contract.save()

    report = generate_report(
        title="Caching Test Report",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
    )

    # Call validation methods multiple times
    result1 = report.has_issues()
    result2 = report.has_issues()
    counts1 = report.get_issue_counts()
    counts2 = report.get_issue_counts()
    warnings1 = report.validation_warnings
    warnings2 = report.validation_warnings

    # All calls should return identical results
    assert result1 == result2
    assert counts1 == counts2
    assert warnings1 is warnings2  # Same object (cached)


@pytest.mark.django_db
def test_has_issues_returns_false_for_clean_report() -> None:

    home_institution = create_institution_with_identifiers(
        name="Test University",
        ror="https://ror.org/test123",
    )
    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = home_institution
    prefs.save()

    contract = create_contract_with_identifiers(
        name="Valid Contract",
        esac="https://esac.org/id/123",
    )
    contract.start_date = date(2024, 1, 1)
    contract.end_date = date(2024, 12, 31)
    contract.save()

    doi_type, _ = LinkType.objects.get_or_create(name="DOI")
    publication = modelfactory.publication(title="Valid Publication")
    Link.objects.create(
        publication=publication,
        type=doi_type,
        value="10.1234/test.123",
    )

    report = generate_report(
        title="Clean Report",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
    )

    assert report.has_issues() is False
    counts = report.get_issue_counts()
    assert counts["errors"] == 0
    assert counts["warnings"] == 0


@pytest.mark.django_db
def test_get_issue_counts_separates_errors_and_warnings() -> None:

    # Create publications without DOI (warning)
    for i in range(3):
        fr = modelfactory.fundingrequest(title=f"Pub {i}")
        # Remove factory DOI to test missing DOI validation
        fr.publication.links.filter(type__name="DOI").delete()
        create_publication_with_invoice(
            fr.publication,
            invoice_date=date(2024, 6, 15),
            invoice_number=f"INV-PUB-{i}",
            cost_amount=Decimal("1500.00"),
        )

    # Create contracts without ESAC ID (error)
    for i in range(2):
        contract = modelfactory.contract()
        contract.start_date = date(2024, 1, 1)
        contract.end_date = date(2024, 12, 31)
        contract.save()

        creditor = create_creditor(name=f"Creditor {i}")
        invoice = create_invoice(
            creditor=creditor,
            invoice_date=date(2024, 6, 1),
            number=f"INV-CONTRACT-{i}",
        )
        create_position(
            invoice=invoice,
            contract=contract,
            cost_amount=Decimal("5000.00"),
            cost_type="read",
        )

    report = generate_report(
        title="Mixed Issues Report",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
    )

    counts = report.get_issue_counts()

    # Should have warnings for missing DOIs
    assert counts["warnings"] >= 3
    # Should have errors for missing ESAC IDs
    assert counts["errors"] >= 2
    # Should have issues
    assert report.has_issues() is True
