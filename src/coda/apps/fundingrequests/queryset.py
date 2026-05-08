from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models

from coda.apps.publications.models import Publication

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


class FundingRequestManager(models.Manager["FundingRequest"]):
    def get_queryset(self) -> FundingRequestQuerySet:
        return FundingRequestQuerySet(self.model, using=self._db)
