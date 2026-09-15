"""Union semantics of OpenCostReport.has_issues()/get_issue_counts().

While the report carries both the legacy ``errors_count``/``warnings_count``
columns and the new ``issues`` JSON, the JSON is authoritative when present and
the columns serve as fallback for rows generated before it existed. Both
answers must agree for legacy, dual-write, and issues-only rows.
"""

from dataclasses import asdict
from datetime import date
from typing import Any, Literal

import pytest

from coda.apps.opencost.issues import ValidationWarning
from coda.apps.opencost.models import OpenCostReport


def warning(level: Literal["error", "warning"]) -> dict[str, Any]:
    """Serialize a ValidationWarning exactly like generation will store it."""
    return asdict(ValidationWarning(level=level, message="msg", entity_type="global"))


def make_report(**kwargs: Any) -> OpenCostReport:
    return OpenCostReport(
        title="Report",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        **kwargs,
    )


def test_issues_only_row_derives_counts_from_json() -> None:
    report = make_report(
        errors_count=0,
        warnings_count=0,
        issues=[warning("error"), warning("error"), warning("warning")],
    )
    assert report.get_issue_counts() == {"errors": 2, "warnings": 1}
    assert report.has_issues() is True


def test_legacy_counts_only_row_uses_columns() -> None:
    report = make_report(errors_count=3, warnings_count=5, issues=[])
    assert report.get_issue_counts() == {"errors": 3, "warnings": 5}
    assert report.has_issues() is True


def test_dual_write_consistent_row_answers_identically_either_way() -> None:
    issues = [warning("error"), warning("error"), warning("warning")]
    report = make_report(errors_count=2, warnings_count=1, issues=issues)
    # Identical answer whether derived from the JSON or read off the columns.
    assert report.get_issue_counts() == {"errors": 2, "warnings": 1}
    assert report.get_issue_counts() == {
        "errors": report.errors_count,
        "warnings": report.warnings_count,
    }
    assert report.has_issues() is True


def test_empty_row_reports_no_issues() -> None:
    report = make_report(errors_count=0, warnings_count=0, issues=[])
    assert report.get_issue_counts() == {"errors": 0, "warnings": 0}
    assert report.has_issues() is False


def test_nonempty_json_with_zero_columns_still_flags_issues() -> None:
    """A warning-only issues JSON must flag the report even with zero columns."""
    report = make_report(errors_count=0, warnings_count=0, issues=[warning("warning")])
    assert report.has_issues() is True
    assert report.get_issue_counts() == {"errors": 0, "warnings": 1}


@pytest.mark.django_db
def test_new_fields_round_trip_through_the_database() -> None:
    report = OpenCostReport.objects.create(
        title="Generated",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        xml_content="<openCost/>",
        issues=[warning("error"), warning("warning")],
    )
    reloaded = OpenCostReport.objects.get(pk=report.pk)
    assert reloaded.xml_content == "<openCost/>"
    assert reloaded.get_issue_counts() == {"errors": 1, "warnings": 1}
    assert reloaded.has_issues() is True


@pytest.mark.django_db
def test_created_report_defaults_to_nothing_exportable_and_no_issues() -> None:
    report = OpenCostReport.objects.create(
        title="Bare",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
    )
    assert report.xml_content == ""
    assert report.issues == []
    assert report.has_issues() is False
