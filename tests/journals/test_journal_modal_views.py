import re

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__click_on_new_journal_from_funding_request__returns_modal_with_journal_form_and_correct_context(
    client: Client,
) -> None:
    response = client.get(reverse("publishing:journals:create_modal"))

    assert response.status_code == 200
    assert "partials/entity_creation_modal.html" in [t.name for t in response.templates]
    assert "form" in response.context
    assert response.context["entity_name"] == "Journal"
    assert response.context["entity_create_url"] == "publishing:journals:create_modal_submit"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__valid_journal_entered__click_create_button__creates_journal_and_returns_success_template(
    client: Client,
) -> None:
    publisher = Publisher.objects.create(name="Test Publisher")
    journal_title = "Nature"
    eissn = "1476-4687"

    response = client.post(
        reverse("publishing:journals:create_modal_submit"),
        {"title": journal_title, "eissn": eissn, "publisher": publisher.pk},
    )

    assert Journal.objects.filter(title=journal_title, eissn=eissn).exists()
    journal = Journal.objects.get(title=journal_title, eissn=eissn)
    assert journal.publisher == publisher

    assert response.status_code == 200
    assert "journals/partials/journal_create_success.html" in [t.name for t in response.templates]
    assert response.context["journal"] == journal

    content = response.content.decode()
    assert 'id="entity-creation-modal-wrapper"' in content
    assert 'hx-swap-oob="true"' in content
    assert 'id="journal-search-results"' in content
    assert 'id="journal_title"' in content
    assert journal_title in content
    assert re.search(
        rf'<input\s+type="radio"\s+name="journal"\s+value="{journal.pk}"\s+checked>', content
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invalid_journal_entered__click_create_button__returns_modal_with_errors(
    client: Client,
) -> None:
    response = client.post(
        reverse("publishing:journals:create_modal_submit"),
        {"title": "", "eissn": "", "publisher": ""},
    )

    assert Journal.objects.count() == 0

    assert response.status_code == 200
    assert "partials/entity_creation_modal.html" in [t.name for t in response.templates]
    assert "form" in response.context
    assert response.context["form"].errors


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_publisher_from_journal_modal__updates_publisher_dropdown_and_closes_nested_modal(
    client: Client,
) -> None:
    # Step 1: Get the journal creation modal
    journal_modal_response = client.get(reverse("publishing:journals:create_modal"))
    assert journal_modal_response.status_code == 200

    content = journal_modal_response.content.decode()
    assert re.search(
        r'<button[^>]*hx-get="/publishing/publishers/create-modal/\?context=journal_modal"[^>]*>.*?New Publisher.*?</button>',
        content,
        re.DOTALL,
    )
    assert re.search(r'<div[^>]*id="nested-entity-creation-modal-wrapper"[^>]*>', content)

    # Step 2: From within journal modal, click "New Publisher" to get publisher modal
    publisher_modal_response = client.get(
        reverse("publishing:publishers:create_modal") + "?context=journal_modal"
    )
    assert publisher_modal_response.status_code == 200
    assert "partials/entity_creation_modal.html" in [
        t.name for t in publisher_modal_response.templates
    ]

    # Step 3: Create the publisher (with context parameter)
    publisher_name = "New Test Publisher"
    publisher_create_response = client.post(
        reverse("publishing:publishers:create_modal_submit") + "?context=journal_modal",
        {"name": publisher_name},
    )

    assert Publisher.objects.filter(name=publisher_name).exists()
    publisher = Publisher.objects.get(name=publisher_name)
    assert publisher_create_response.status_code == 200

    # Verify the response clears the nested wrapper and updates publisher dropdown
    publisher_content = publisher_create_response.content.decode()
    assert re.search(r'<div[^>]*id="nested-entity-creation-modal-wrapper"[^>]*>', publisher_content)
    assert re.search(r'<select[^>]*id="id_publisher"[^>]*>', publisher_content)
    assert re.search(
        rf'<option\s+value="{publisher.pk}"\s+selected>\s*{re.escape(publisher_name)}\s*</option>',
        publisher_content,
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_journal_with_new_publisher_in_modal__creates_both_entities(
    client: Client,
) -> None:
    publisher_name = "Test Publisher for Journal"
    publisher_create_response = client.post(
        reverse("publishing:publishers:create_modal_submit") + "?context=journal_modal",
        {"name": publisher_name},
    )

    assert publisher_create_response.status_code == 200
    assert Publisher.objects.filter(name=publisher_name).exists()
    publisher = Publisher.objects.get(name=publisher_name)

    journal_title = "Science"
    eissn = "1095-9203"

    journal_create_response = client.post(
        reverse("publishing:journals:create_modal_submit"),
        {"title": journal_title, "eissn": eissn, "publisher": publisher.pk},
    )

    assert journal_create_response.status_code == 200
    assert Journal.objects.filter(title=journal_title, eissn=eissn).exists()
    journal = Journal.objects.get(title=journal_title, eissn=eissn)
    assert journal.publisher == publisher
