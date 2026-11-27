from typing import Any

import pytest
from django.db import IntegrityError
from django_test_migrations.contrib.unittest_case import MigratorTestCase


def _create_funding_request(FundingRequest: Any, labels: Any = None) -> Any:
    count = FundingRequest.objects.count() + 1
    apps = FundingRequest._meta.apps
    Publication = apps.get_model("publications", "Publication")
    AttachedConcept = apps.get_model("publications", "PublicationAttachedConcept")
    concept = AttachedConcept.objects.create(
        entity_id="fd0febd8-2218-4327-a517-d78b7f8f58ff", vocabulary_id=0
    )
    publication = Publication.objects.create(
        title=f"Publication {count}", subject_area=concept, publication_type=concept
    )
    review = apps.get_model("fundingrequests", "FundingRequestReview").objects.create()
    fr = FundingRequest.objects.create(
        request_id=f"fr-{count}",
        request_date="2026-01-01",
        request_number=f"REQ-{count:03d}",
        estimated_cost=100,
        estimated_cost_currency="EUR",
        publication=publication,
        review=review,
    )
    if labels:
        fr.labels.set(labels)
    return fr


@pytest.mark.django_db
class TestCollapseDuplicateLabelsForward(MigratorTestCase):
    """Forward migration: merge same-name labels before unique constraint."""

    migrate_from = ("fundingrequests", "0037_add_archived_at_to_fundingorganization")
    migrate_to = ("fundingrequests", "0038_collapse_duplicate_labels")

    def prepare(self) -> None:
        """Create duplicate labels with attached funding requests."""
        Label = self.old_state.apps.get_model("fundingrequests", "Label")
        FundingRequest = self.old_state.apps.get_model("fundingrequests", "FundingRequest")

        # "Alpha": three duplicates. The one with the most requests (id 3) survives.
        alpha_a = Label.objects.create(name="Alpha", hexcolor="#FF0000")
        alpha_b = Label.objects.create(name="Alpha", hexcolor="#00FF00")
        alpha_c = Label.objects.create(name="Alpha", hexcolor="#0000FF")
        for _ in range(3):
            _create_funding_request(FundingRequest, labels=[alpha_c])
        _create_funding_request(FundingRequest, labels=[alpha_a])
        _create_funding_request(FundingRequest, labels=[alpha_b])
        self.alpha_survivor_pk = alpha_c.pk
        self.alpha_dead_pks = [alpha_a.pk, alpha_b.pk]

        # "Beta": tie on request count (1 each) -> lowest id survives.
        beta_a = Label.objects.create(name="Beta", hexcolor="#123456")
        beta_b = Label.objects.create(name="Beta", hexcolor="#654321")
        _create_funding_request(FundingRequest, labels=[beta_b])
        _create_funding_request(FundingRequest, labels=[beta_a])
        self.beta_survivor_pk = beta_a.pk

        # "Gamma": no duplicates, untouched.
        self.gamma_pk = Label.objects.create(name="Gamma", hexcolor="#ABCDEF").pk

    def test_survivor_is_label_with_most_requests(self) -> None:
        Label = self.new_state.apps.get_model("fundingrequests", "Label")
        label = Label.objects.get(name="Alpha")
        assert label.pk == self.alpha_survivor_pk
        assert label.requests.count() == 5

    def test_survivor_inherits_requests_of_duplicates(self) -> None:
        FundingRequest = self.new_state.apps.get_model("fundingrequests", "FundingRequest")
        attached = FundingRequest.objects.filter(labels__pk=self.alpha_survivor_pk)
        assert attached.count() == 5

    def test_duplicates_are_deleted(self) -> None:
        Label = self.new_state.apps.get_model("fundingrequests", "Label")
        assert not Label.objects.filter(pk__in=self.alpha_dead_pks).exists()

    def test_tie_broken_by_lowest_id(self) -> None:
        Label = self.new_state.apps.get_model("fundingrequests", "Label")
        label = Label.objects.get(name="Beta")
        assert label.pk == self.beta_survivor_pk
        # Both duplicates had one request each; the survivor inherits the other's.
        assert label.requests.count() == 2

    def test_unique_labels_untouched(self) -> None:
        Label = self.new_state.apps.get_model("fundingrequests", "Label")
        gamma = Label.objects.get(pk=self.gamma_pk)
        assert gamma.name == "Gamma"
        assert gamma.hexcolor == "#ABCDEF"

    def test_name_is_unique_after_migration(self) -> None:
        Label = self.new_state.apps.get_model("fundingrequests", "Label")
        with pytest.raises(IntegrityError):
            Label.objects.create(name="Alpha", hexcolor="#000000")


@pytest.mark.django_db
class TestCollapseDuplicateLabelsNoDuplicates(MigratorTestCase):
    """Forward migration: no-op when no duplicate names exist."""

    migrate_from = ("fundingrequests", "0037_add_archived_at_to_fundingorganization")
    migrate_to = ("fundingrequests", "0038_collapse_duplicate_labels")

    def prepare(self) -> None:
        Label = self.old_state.apps.get_model("fundingrequests", "Label")
        self.one = Label.objects.create(name="One", hexcolor="#111111")
        self.two = Label.objects.create(name="Two", hexcolor="#222222")

    def test_all_labels_preserved(self) -> None:
        Label = self.new_state.apps.get_model("fundingrequests", "Label")
        assert Label.objects.count() == 2
        assert Label.objects.get(pk=self.one.pk).hexcolor == "#111111"
        assert Label.objects.get(pk=self.two.pk).hexcolor == "#222222"
