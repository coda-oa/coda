import pytest
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from coda.apps.institutions.models import Institution

from coda.apps.institutions.views import request_set_successor


def create_institution_scenario() -> tuple[Institution, Institution]:
    active = Institution.objects.create(name="Active University")
    archived = Institution.objects.create(name="Archived University", archived_at=timezone.now())
    return active, archived


def assert_content_contains(content: str, *items: str) -> None:
    for item in items:
        assert item in content


def assert_content_excludes(content: str, *items: str) -> None:
    for item in items:
        assert item not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__institution_detail_view__shows_institution_name(client: Client) -> None:
    institution = Institution.objects.create(name="Test University")

    response = client.get(reverse("institutions:detail", kwargs={"pk": institution.pk}))

    assert "Test University" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__institution_detail_view__shows_archived_status(client: Client) -> None:
    _, archived = create_institution_scenario()

    response = client.get(reverse("institutions:detail", kwargs={"pk": archived.pk}))

    assert response.status_code == 200
    content = response.content.decode()
    assert '<span class="pill danger">Archived</span>' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__institution_edit_view__shows_archived_status(client: Client) -> None:
    _, archived = create_institution_scenario()

    response = client.get(reverse("institutions:edit", kwargs={"pk": archived.pk}))

    content = response.content.decode()
    assert '<span class="pill danger">Archived</span>' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__institution_detail_view__shows_can_delete_flag(client: Client) -> None:
    institution = Institution.objects.create(name="Test University")

    response = client.get(reverse("institutions:detail", kwargs={"pk": institution.pk}))

    assert "can_delete" in response.context or "Delete" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__institution_detail_view__shows_relationships(client: Client) -> None:
    parent = Institution.objects.create(name="Parent University")
    _ = Institution.objects.create(name="Child Campus", parent=parent)

    response = client.get(reverse("institutions:detail", kwargs={"pk": parent.pk}))

    assert "relationships" in response.context
    assert response.context["relationships"].children.exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__set_successor_with_create_new_institution__click_archive__creates_new_successor_and_archives_institution(
    client: Client,
) -> None:
    institution = Institution.objects.create(name="Old University")

    response = client.post(
        reverse("institutions:set_successor", kwargs={"pk": institution.pk}),
        {"successor_type": "create_new", "new_name": "New University"},
    )

    assert response.status_code == 302
    institution.refresh_from_db()
    assert institution.archived_at is not None
    assert institution.succeeded_by.count() == 1
    successor = institution.succeeded_by.first()
    assert successor is not None
    assert successor.name == "New University"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__set_successor_with_selecting_existing_successor__click_archive__archives_institution_and_sets_existing_successor(
    client: Client,
) -> None:
    old_institution = Institution.objects.create(name="Old University")
    new_institution = Institution.objects.create(name="New University")

    response = client.post(
        reverse("institutions:set_successor", kwargs={"pk": old_institution.pk}),
        {"successor_type": "select_existing", "successor_id": new_institution.pk},
    )

    assert response.status_code == 302
    old_institution.refresh_from_db()
    assert old_institution.archived_at is not None
    assert new_institution in old_institution.succeeded_by.all()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__set_successor__already_archived__redirects_with_error(
    client: Client,
) -> None:
    _, archived = create_institution_scenario()

    response = client.post(
        reverse("institutions:set_successor", kwargs={"pk": archived.pk}),
        {"successor_type": "create_new", "new_name": "New University"},
    )

    assert response.status_code == 302


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__institution_with_no_relationships__click_delete__deletes_successfully(
    client: Client,
) -> None:
    institution = Institution.objects.create(name="Test University")

    response = client.post(reverse("institutions:delete", kwargs={"pk": institution.pk}))

    assert response.status_code == 200
    assert response["HX-Redirect"] == reverse("institutions:list")
    assert not Institution.all_objects.filter(pk=institution.pk).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__institution_with_children__click_delete__fails(client: Client) -> None:
    parent = Institution.objects.create(name="Parent University")
    _ = Institution.objects.create(name="Child Campus", parent=parent)

    response = client.post(reverse("institutions:delete", kwargs={"pk": parent.pk}))

    assert response.status_code == 200
    assert response["HX-Redirect"] == reverse("institutions:detail", kwargs={"pk": parent.pk})
    assert Institution.all_objects.filter(pk=parent.pk).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__institution_with_archived_status__click_delete__cannot_delete(client: Client) -> None:
    _, archived = create_institution_scenario()

    response = client.post(reverse("institutions:delete", kwargs={"pk": archived.pk}))

    assert response.status_code == 200
    assert response["HX-Redirect"] == reverse("institutions:detail", kwargs={"pk": archived.pk})
    assert Institution.all_objects.filter(pk=archived.pk).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__excludes_archived_by_default(client: Client) -> None:
    active, archived = create_institution_scenario()

    response = client.get(reverse("institutions:list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert_content_contains(content, active.name)
    assert_content_excludes(content, archived.name)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__includes_archived_when_requested(client: Client) -> None:
    active, archived = create_institution_scenario()

    response = client.get(reverse("institutions:list"), {"include_archived": "on"})

    content = response.content.decode()
    assert_content_contains(content, active.name, archived.name)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__search_with_archived_filter(client: Client) -> None:
    active, archived = create_institution_scenario()

    response = client.get(
        reverse("institutions:list"), {"name": "University", "include_archived": "on"}
    )

    content = response.content.decode()
    assert_content_contains(content, active.name, archived.name)


@pytest.mark.django_db
def test__successor_modal__excludes_current_institution_from_successor_dropdown() -> None:
    institution = Institution.objects.create(name="Test University")
    other_institution = Institution.objects.create(name="Other University")

    request = RequestFactory().get("/")
    response = request_set_successor(request, pk=institution.pk)
    html = response.content.decode()

    dropdown_start = html.index('id="successor_id"')
    dropdown_end = html.index("</select>", dropdown_start)
    dropdown_html = html[dropdown_start:dropdown_end]

    assert other_institution.name in dropdown_html
    assert institution.name not in dropdown_html
