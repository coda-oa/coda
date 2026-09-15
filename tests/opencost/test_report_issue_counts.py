"""Semantics of OpenCostReport.has_issues()/get_issue_counts().

The stored ``issues`` JSON is the single source: the counts are exactly the log's
contents, and nothing is kept alongside that could disagree with it.
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


def test_issue_log_derives_counts_from_json() -> None:
    report = make_report(issues=[warning("error"), warning("error"), warning("warning")])
    assert report.get_issue_counts() == {"errors": 2, "warnings": 1}
    assert report.has_issues() is True


def test_empty_issue_log_reports_no_issues() -> None:
    report = make_report(issues=[])
    assert report.get_issue_counts() == {"errors": 0, "warnings": 0}
    assert report.has_issues() is False


def test_missing_or_null_issue_log_reports_no_issues() -> None:
    """A log that never made it in (JSON null) reads as empty, not as an error."""
    report = make_report(issues=None)
    assert report.get_issue_counts() == {"errors": 0, "warnings": 0}
    assert report.has_issues() is False


def test_log_of_unknown_level_entries_counts_as_no_issues() -> None:
    """Malformed entries carry no recognizable level: they count for nothing."""
    report = make_report(issues=[{"level": "info", "message": "msg"}, {"message": "msg"}])
    assert report.get_issue_counts() == {"errors": 0, "warnings": 0}
    assert report.has_issues() is False


def test_warning_only_log_still_flags_the_report() -> None:
    report = make_report(issues=[warning("warning")])
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
