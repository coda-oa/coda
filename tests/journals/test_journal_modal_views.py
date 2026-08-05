import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.journals import services as journal_services
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from tests import modelfactory


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
    assert "partials/entity_creation_modal.html" in [
        t.name for t in journal_modal_response.templates
    ]

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
    assert publisher_create_response.context["publisher"] == publisher


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


@pytest.mark.django_db
@pytest.mark.parametrize(
    "search_term",
    ["", "   ", "\t"],
)
def test__find_by_title__empty_or_whitespace__returns_all_journals(search_term: str) -> None:
    publisher = modelfactory.publisher()
    modelfactory.journal(title="Nature Communications", publisher_id=publisher.pk)
    modelfactory.journal(title="Science Advances", publisher_id=publisher.pk)

    results = list(journal_services.find_by_title(search_term))

    assert len(results) == 2


@pytest.mark.django_db
def test__find_by_title__multi_word_search__each_word_matches_independently() -> None:
    publisher = modelfactory.publisher()
    modelfactory.journal(title="Nature Communications", publisher_id=publisher.pk)

    results = list(journal_services.find_by_title("Nat Comm"))

    assert len(results) == 1
    assert results[0].title == "Nature Communications"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_list_view__multi_word_search__each_word_matches_independently(
    client: Client,
) -> None:
    publisher = modelfactory.publisher()
    modelfactory.journal(title="Nature Communications", publisher_id=publisher.pk)

    response = client.get(reverse("publishing:journals:list"), {"query": "Nat Comm"})

    assert response.status_code == 200
    assert "Nature Communications" in response.content.decode()
