import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from coda.apps.institutions.models import Institution
from coda.apps.preferences.models import GlobalPreferences


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

    # HTMX redirect response
    assert response.status_code == 200
    assert "HX-Redirect" in response
    institution.refresh_from_db()
    assert institution.archived_at is not None
    # Check that the successor was created
    successor = Institution.objects.filter(name="New University").first()
    assert successor is not None
    assert successor.archived_at is None


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

    # HTMX redirect response
    assert response.status_code == 200
    assert "HX-Redirect" in response
    old_institution.refresh_from_db()
    assert old_institution.archived_at is not None
    # The new institution should still be active (not archived)
    new_institution.refresh_from_db()
    assert new_institution.archived_at is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__set_successor__already_archived__shows_error_in_modal(
    client: Client,
) -> None:
    _, archived = create_institution_scenario()

    response = client.post(
        reverse("institutions:set_successor", kwargs={"pk": archived.pk}),
        {"successor_type": "create_new", "new_name": "New University"},
    )

    # Should re-render modal with error
    assert response.status_code == 200
    html = response.content.decode()
    assert "Institution is already archived" in html
    assert "<dialog open>" in html


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
@pytest.mark.usefixtures("logged_in")
def test__list_view__multi_word_search__each_word_matches_independently(client: Client) -> None:
    Institution.objects.create(name="Active University")

    response = client.get(reverse("institutions:list"), {"name": "Act Univ"})

    assert response.status_code == 200
    assert "Active University" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__successor_modal__excludes_current_institution_from_successor_dropdown(
    client: Client,
) -> None:
    institution = Institution.objects.create(name="Test University")
    other_institution = Institution.objects.create(name="Other University")

    response = client.get(
        reverse("institutions:request_set_successor", kwargs={"pk": institution.pk})
    )
    html = response.content.decode()

    dropdown_start = html.index('id="successor_id"')
    dropdown_end = html.index("</select>", dropdown_start)
    dropdown_html = html[dropdown_start:dropdown_end]

    assert other_institution.name in dropdown_html
    assert institution.name not in dropdown_html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__successor_modal__normal_institution__shows_all_archiving_options(client: Client) -> None:
    institution = Institution.objects.create(name="Test University")

    response = client.get(
        reverse("institutions:request_set_successor", kwargs={"pk": institution.pk})
    )

    assert response.context["is_home_institution"] is False

    html = response.content.decode()
    assert 'value="no_successor"' in html
    assert 'value="create_new"' in html
    assert 'value="select_existing"' in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__successor_modal__home_institution__hides_no_successor_option(client: Client) -> None:
    institution = Institution.objects.create(name="Home University")
    GlobalPreferences.objects.create(home_institution=institution)

    response = client.get(
        reverse("institutions:request_set_successor", kwargs={"pk": institution.pk})
    )

    assert response.context["is_home_institution"] is True

    html = response.content.decode()
    assert 'value="no_successor"' not in html
    assert "radio-no-successor" not in html

    assert 'value="create_new"' in html
    assert 'value="select_existing"' in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__successor_modal__home_institution__shows_warning_message(client: Client) -> None:
    institution = Institution.objects.create(name="Home University")
    GlobalPreferences.objects.create(home_institution=institution)

    response = client.get(
        reverse("institutions:request_set_successor", kwargs={"pk": institution.pk})
    )

    assert response.context["is_home_institution"] is True

    html = response.content.decode()
    assert "currently set as your home institution" in html
    assert "must select a successor" in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__successor_modal__institution_with_children__shows_warning_message(client: Client) -> None:
    parent = Institution.objects.create(name="Parent University")
    Institution.objects.create(name="Child Department", parent=parent)

    response = client.get(reverse("institutions:request_set_successor", kwargs={"pk": parent.pk}))

    assert response.context["has_children"] is True

    html = response.content.decode()
    assert "has child institutions" in html
    assert "children will be archived as well" in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__successor_modal__institution_without_children__shows_no_successor_option(
    client: Client,
) -> None:
    institution = Institution.objects.create(name="Solo Institution")

    response = client.get(
        reverse("institutions:request_set_successor", kwargs={"pk": institution.pk})
    )

    assert response.context["has_children"] is False

    html = response.content.decode()
    assert 'value="no_successor"' in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__archive_with_empty_new_name__shows_inline_error_in_modal(client: Client) -> None:
    institution = Institution.objects.create(name="Test University")

    response = client.post(
        reverse("institutions:set_successor", kwargs={"pk": institution.pk}),
        {"successor_type": "create_new", "new_name": ""},
    )

    assert response.status_code == 200

    assert response.context["form_data"]["successor_type"] == "create_new"
    assert response.context["form_data"]["new_name"] == ""

    html = response.content.decode()

    assert 'aria-invalid="true"' in html
    assert "New institution name is required" in html
    assert "<dialog open>" in html


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__archive_with_no_successor_selected__shows_inline_error_in_modal(client: Client) -> None:
    institution = Institution.objects.create(name="Test University")

    response = client.post(
        reverse("institutions:set_successor", kwargs={"pk": institution.pk}),
        {"successor_type": "select_existing", "successor_id": ""},
    )

    assert response.status_code == 200

    assert response.context["form_data"]["successor_type"] == "select_existing"
    assert response.context["form_data"]["successor_id"] == ""

    html = response.content.decode()
    assert 'aria-invalid="true"' in html
    assert "Please select a successor institution" in html
    assert "<dialog open>" in html
