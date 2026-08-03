import pytest
from django.utils import timezone

from coda.apps.fundingrequests.services.funder_services import can_merge_funding_organization
from tests import modelfactory


@pytest.mark.django_db
class TestCanMergeFundingOrganization:
    """Tests for merge permission checks."""

    def test__can_merge__returns_true_when_both_active_and_different(self) -> None:
        """Should allow merge when both organizations are active and different."""
        source = modelfactory.funding_organization(name="Source Org")
        target = modelfactory.funding_organization(name="Target Org")

        can_merge, reasons = can_merge_funding_organization(source, target)

        assert can_merge is True
        assert len(reasons) == 0

    def test__can_merge__returns_false_when_source_equals_target(self) -> None:
        """Should not allow merging an organization into itself."""
        org = modelfactory.funding_organization(name="Same Org")

        can_merge, reasons = can_merge_funding_organization(org, org)

        assert can_merge is False
        assert len(reasons) == 1
        assert "itself" in reasons[0].lower()

    def test__can_merge__returns_false_when_source_is_archived(self) -> None:
        """Should not allow merging an archived organization."""
        source = modelfactory.funding_organization(name="Archived Org")
        source.archived_at = timezone.now()
        source.save()
        target = modelfactory.funding_organization(name="Target Org")

        can_merge, reasons = can_merge_funding_organization(source, target)

        assert can_merge is False
        assert len(reasons) == 1
        assert "archived" in reasons[0].lower()

    def test__can_merge__returns_false_when_target_is_archived(self) -> None:
        """Should not allow merging into an archived organization."""
        source = modelfactory.funding_organization(name="Source Org")
        target = modelfactory.funding_organization(name="Archived Org")
        target.archived_at = timezone.now()
        target.save()

        can_merge, reasons = can_merge_funding_organization(source, target)

        assert can_merge is False
        assert len(reasons) == 1
        assert "archived" in reasons[0].lower()

    def test__can_merge__returns_multiple_reasons_when_multiple_issues(self) -> None:
        """Should return multiple reasons when multiple issues exist."""
        org = modelfactory.funding_organization(name="Same Org")
        org.archived_at = timezone.now()
        org.save()

        can_merge, reasons = can_merge_funding_organization(org, org)

        assert can_merge is False
        assert len(reasons) == 2
