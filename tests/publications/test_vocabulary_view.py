import pytest

from django.urls import reverse
from django.test import Client
from coda.apps.publications.models import Vocabulary as VocabularyModel

from coda.domain.vocabulary import VocabularyId


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_limited_button__redirects_to_edit_view__has_base_vocabulary_in_context(
    client: Client,
) -> None:
    base_model = VocabularyModel.objects.create(name="Base Vocabulary", version="1.0")
    base_vocabulary_id = VocabularyId(base_model.pk)

    response = client.get(
        reverse("publications:vocabulary_create_limited", kwargs={"pk": base_vocabulary_id}),
    )

    assert response.status_code == 200
    assert "vocabulary" in response.context
    limited = response.context["vocabulary"]
    assert limited.base_vocabulary.id == base_vocabulary_id

    with pytest.raises(VocabularyModel.DoesNotExist):
        VocabularyModel.objects.get(name=limited.name)
