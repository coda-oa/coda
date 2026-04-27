from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models
from django.db.models import Prefetch

from coda.apps.authors.models import Author as AuthorModel
from coda.apps.publications.models import Publication
from coda.apps.publications.models import Vocabulary as VocabularyModel

if TYPE_CHECKING:
    from coda.apps.fundingrequests.models import FundingRequest  # noqa


class FundingRequestQuerySet(models.QuerySet["FundingRequest"]):
    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        publication_ids = self.values_list("publication_id", flat=True)
        publication_qs = Publication.objects.filter(id__in=publication_ids)
        publication_deletions = [publication_qs.delete()[1]] if publication_ids else []

        deleted_entity_names = {
            key for deletion in publication_deletions for key in deletion.keys()
        }
        counted_deletions = {entity_name: 0 for entity_name in deleted_entity_names}
        counted_deletions.update(
            {
                entity_name: sum(deletion.get(entity_name, 0) for deletion in publication_deletions)
                for entity_name in deleted_entity_names
            }
        )

        _, fundingrequest_deletions = super().delete(*args, **kwargs)
        counted_deletions = {
            key: counted_deletions.get(key, 0) + fundingrequest_deletions.get(key, 0)
            for key in set(counted_deletions) | set(fundingrequest_deletions)
        }

        return (sum(counted_deletions.values()), counted_deletions)

    def for_domain(self) -> FundingRequestQuerySet:
        """Prefetch all relations needed to hydrate a FundingRequest domain object."""
        return self.select_related(
            "publication",
            "publication__article_journal",
            "publication__article_journal__publisher",
            "publication__monograph_publisher",
            "publication__publication_type",
            "publication__subject_area",
            "extra_contact",
            "review",
        ).prefetch_related(
            "external_funding",
            "publication__attached_contracts",
            "publication__links__type",
            Prefetch(
                "publication__publication_type__vocabulary",
                queryset=VocabularyModel.objects.for_domain(),
            ),
            Prefetch(
                "publication__subject_area__vocabulary",
                queryset=VocabularyModel.objects.for_domain(),
            ),
            Prefetch(
                "publication__relevant_authors",
                queryset=AuthorModel.objects.for_domain(),
            ),
        )

    def for_detail(self) -> FundingRequestQuerySet:
        """Extend for_domain() with display-only prefetches for the detail view."""
        return self.for_domain().prefetch_related("labels")


class FundingRequestManager(models.Manager["FundingRequest"]):
    def get_queryset(self) -> FundingRequestQuerySet:
        return FundingRequestQuerySet(self.model, using=self._db)

    def for_domain(self) -> FundingRequestQuerySet:
        return self.get_queryset().for_domain()

    def for_detail(self) -> FundingRequestQuerySet:
        return self.get_queryset().for_detail()
