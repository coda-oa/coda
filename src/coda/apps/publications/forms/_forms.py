import datetime
import logging
from collections.abc import Collection, Iterable, Mapping
from typing import Any, cast

from django import forms

from coda.apps import widgets
from coda.apps.formbase import CodaFormBase
from coda.apps.publications.dto import ConceptDto, LinkDto, PublicationMetaDto
from coda.apps.publications.models import LinkType, Publication
from coda.contexts.fundingrequest.services.allowed_vocabularies import AllowedConcepts
from coda.domain.publication import License, OpenAccessType, Published, UnpublishedState, links
from coda.domain.vocabulary import VocabularyConcept

from ._fields import ConceptChoiceField, encode_concept_dto


class PublicationForm(CodaFormBase):
    use_required_attribute = False

    title = forms.CharField(required=True, label="Title*")
    license = forms.ChoiceField(
        choices=((lic.name, lic.value) for lic in License),
        required=True,
        initial=License.Unknown.name,
        label="License*",
    )
    publication_type = ConceptChoiceField(
        concepts=[],
        required=True,
        widget=widgets.SearchSelectWidget,
        label="Publication type*",
    )
    subject_area = ConceptChoiceField(
        concepts=[],
        required=True,
        widget=widgets.SearchSelectWidget,
        label="Subject area*",
    )
    open_access_type = forms.ChoiceField(
        choices=Publication.OA_TYPES,
        required=True,
        initial=OpenAccessType.Closed.name,
        label="Publication open access type*",
    )
    publication_state = forms.ChoiceField(
        choices=Publication.STATES,
        required=True,
        initial=UnpublishedState.Unknown.name,
        label="Publication state*",
    )
    online_publication_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), required=False
    )
    print_publication_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), required=False
    )

    @classmethod
    def from_dto(cls, dto: PublicationMetaDto, allowed: AllowedConcepts) -> "PublicationForm":
        return cls(
            data={
                "title": dto.title,
                "license": dto.license,
                "subject_area": encode_concept_dto(dto.subject_area),
                "publication_type": encode_concept_dto(dto.publication_type),
                "open_access_type": dto.open_access_type,
                "publication_state": dto.publication_state,
                "online_publication_date": dto.online_publication_date,
                "print_publication_date": dto.print_publication_date,
            },
            concepts=allowed,
        )

    def __init__(
        self,
        data: Mapping[str, Any] | None = None,
        concepts: AllowedConcepts = AllowedConcepts((), ()),
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(data, *args, **kwargs)

        self._set_concepts("subject_area", concepts.subject_types)
        self._set_concepts("publication_type", concepts.publication_types)
        logging.debug(
            "PublicationForm initialized with concepts: subject_areas=%s, publication_types=%s",
            concepts.subject_types,
            concepts.publication_types,
        )

        if data:
            _ = self.is_valid()

    def _set_concepts(self, field: str, concepts: Collection[VocabularyConcept] | None) -> None:
        cast(ConceptChoiceField, self.fields[field]).set_vocabulary(concepts)

    def full_clean(self) -> None:
        super().full_clean()
        if not hasattr(self, "cleaned_data"):
            return

        if self.cleaned_data.get("publication_state") != Published.name():
            return

        try:
            online_date = self.cleaned_data.get("online_publication_date")
            print_date = self.cleaned_data.get("print_publication_date")
            Published(online=online_date, print=print_date)
        except ValueError as err:
            self.add_error("online_publication_date", str(err))
            self.add_error("print_publication_date", str(err))

    def is_valid(self) -> bool:
        self.full_clean()
        valid = super().is_valid()
        logging.info("PublicationForm has the following errors %s", self.errors.as_data())
        if self.errors:
            return False

        return valid

    def to_dto(self) -> PublicationMetaDto:
        return PublicationMetaDto(
            title=self.cleaned_data["title"],
            license=self.cleaned_data["license"],
            subject_area=ConceptDto.from_concept(self.cleaned_data["subject_area"]),
            publication_type=ConceptDto.from_concept(self.cleaned_data["publication_type"]),
            open_access_type=self.cleaned_data["open_access_type"],
            publication_state=self.cleaned_data["publication_state"],
            online_publication_date=self.cleaned_data["online_publication_date"],
            print_publication_date=self.cleaned_data["print_publication_date"],
        )

    def _parse_date(self, media: str) -> str:
        key = f"{media}_publication_date"
        if not self.cleaned_data.get(key):
            return ""

        return cast(datetime.date, self.cleaned_data[key]).isoformat()


def _link_type_choices() -> list[tuple[str, str]]:
    return [(lt, lt) for lt in LinkType.objects.values_list("name", flat=True)]


class LinkForm(forms.Form):
    use_required_attribute = False
    link_type = forms.ChoiceField(choices=_link_type_choices)
    link_value = forms.CharField()

    def full_clean(self) -> None:
        super().full_clean()
        if not self.cleaned_data.get("link_type") or not self.cleaned_data.get("link_value"):
            return

        try:
            links.create_link(self.cleaned_data["link_type"], self.cleaned_data["link_value"])
        except ValueError as err:
            self.add_error("link_value", str(err))

    def get_form_data(self) -> LinkDto:
        return LinkDto(
            link_type=self.cleaned_data.get("link_type", self.data.get("link_type", "")),
            link_value=self.cleaned_data.get("link_value", self.data.get("link_value", "")),
        )


def concept_json(concept: VocabularyConcept) -> str:
    return ConceptDto.from_concept(concept).model_dump_json()


def concept_form_values(concepts: Iterable[VocabularyConcept]) -> list[tuple[str, str]]:
    return [(concept_json(c), c.name) for c in concepts]
