from typing import cast

from django.db.models import Prefetch, QuerySet

from coda.apps.mappers import prefixed
from coda.apps.publications.models import Concept as ConceptModel
from coda.apps.publications.models import Vocabulary as VocabularyModel
from coda.domain.vocabulary import (
    ConceptId,
    LimitedVocabulary,
    Vocabulary,
    VocabularyConcept,
    VocabularyId,
    VocabularyProtocol,
)

MAX_VOCABULARY_NESTING_DEPTH = 10


class VocabularyDomainMapper:
    @staticmethod
    def prefetch(
        qs: QuerySet[VocabularyModel],
        prefix: str = "",
        _depth: int = MAX_VOCABULARY_NESTING_DEPTH,
    ) -> QuerySet[VocabularyModel]:
        qs = qs.prefetch_related(
            Prefetch(
                prefixed(prefix, "concepts"),
                queryset=ConceptModel.objects.select_related("parent"),
            ),
        )

        if _depth > 0:
            # Prefetch base_vocabulary for the current vocabulary models.
            # Use base_vocabulary_id (the FK column) so we fetch the actual base
            # vocabularies that limited vocabularies point to, rather than fetching
            # the limited vocabularies themselves.
            base_vocab_ids = qs.values_list("base_vocabulary_id", flat=True)
            qs = qs.prefetch_related(
                Prefetch(
                    prefixed(prefix, "base_vocabulary"),
                    queryset=VocabularyDomainMapper.prefetch(
                        VocabularyModel.objects.filter(pk__in=base_vocab_ids),
                        prefix=prefix,
                        _depth=_depth - 1,
                    ),
                ),
            )

        return qs

    @staticmethod
    def map(v: VocabularyModel) -> VocabularyProtocol:
        if v.is_limited:
            base_vocabulary_model = cast(VocabularyModel, v.base_vocabulary)
            base_vocabulary_domain = VocabularyDomainMapper.map(base_vocabulary_model)
            limited: LimitedVocabulary = LimitedVocabulary(
                id=VocabularyId(v.pk),
                base_vocabulary=base_vocabulary_domain,
                name=v.name,
                version=base_vocabulary_model.version,
            )
            for c in v.concepts.all():
                limited.disallow(c.concept_id)
            return limited
        else:
            return Vocabulary(
                id=VocabularyId(v.pk),
                name=v.name,
                version=v.version,
                concepts=[
                    VocabularyConcept(
                        id=ConceptId(str(c.entity_id)),
                        concept_id=c.concept_id,
                        vocabulary=VocabularyId(v.pk),
                        name=c.name,
                        description=c.hint,
                        parent=ConceptId(str(c.parent.entity_id)) if c.parent else None,
                    )
                    for c in v.concepts.all()
                ],
            )
