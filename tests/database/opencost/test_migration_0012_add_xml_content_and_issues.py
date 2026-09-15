import datetime

import pytest
from django_test_migrations.contrib.unittest_case import MigratorTestCase


@pytest.mark.django_db
class TestAddXmlContentAndIssuesForward(MigratorTestCase):
    """Forward migration 0011 -> 0012: report gains xml_content + issues columns."""

    migrate_from = ("opencost", "0011_remove_opencostreport_xml_content")
    migrate_to = ("opencost", "0012_add_opencostreport_xml_content_and_issues")

    def prepare(self) -> None:
        """Create a legacy report before the columns exist."""
        Report = self.old_state.apps.get_model("opencost", "OpenCostReport")
        Report.objects.create(
            title="Legacy report",
            period_start=datetime.date(2024, 1, 1),
            period_end=datetime.date(2024, 12, 31),
        )

    def test_existing_rows_get_column_defaults(self) -> None:
        Report = self.new_state.apps.get_model("opencost", "OpenCostReport")
        report = Report.objects.get(title="Legacy report")
        assert report.xml_content == ""
        assert report.issues == []

    def test_new_columns_accept_values(self) -> None:
        Report = self.new_state.apps.get_model("opencost", "OpenCostReport")
        report = Report.objects.create(
            title="Generated report",
            period_start=datetime.date(2024, 1, 1),
            period_end=datetime.date(2024, 12, 31),
            xml_content="<openCost/>",
            issues=[{"level": "error", "message": "boom"}],
        )
        report.refresh_from_db()
        assert report.xml_content == "<openCost/>"
        assert report.issues == [{"level": "error", "message": "boom"}]


@pytest.mark.django_db
class TestAddXmlContentAndIssuesReverse(MigratorTestCase):
    """Reverse migration 0012 -> 0011: both columns are dropped without error."""

    migrate_from = ("opencost", "0012_add_opencostreport_xml_content_and_issues")
    migrate_to = ("opencost", "0011_remove_opencostreport_xml_content")

    def prepare(self) -> None:
        """Create a report with the new columns populated."""
        Report = self.old_state.apps.get_model("opencost", "OpenCostReport")
        Report.objects.create(
            title="Generated report",
            period_start=datetime.date(2024, 1, 1),
            period_end=datetime.date(2024, 12, 31),
            xml_content="<openCost/>",
            issues=[{"level": "error", "message": "boom"}],
        )

    def test_columns_are_dropped_and_rows_survive(self) -> None:
        Report = self.new_state.apps.get_model("opencost", "OpenCostReport")
        field_names = {field.name for field in Report._meta.get_fields()}
        assert "xml_content" not in field_names
        assert "issues" not in field_names
        assert Report.objects.filter(title="Generated report").count() == 1
