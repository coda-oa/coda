from collections.abc import Generator

import pytest
from django.test import Client
from django.urls import reverse

from coda import formdata
from coda.apps.fundingrequests.models import (
    FundingOrganization,
    FundingOrganizationLink,
    FundingOrganizationLinkType,
)
from coda.apps.fundingrequests.views.doi_preview import (
    AddFunding,
    DeleteFunding,
    DOIImportInputView,
    DOIPreviewDetailView,
    DOIPreviewSaveView,
)
from coda.contexts.publication.services.doi_client import crossref
from coda.domain.contract import PublisherId
from tests import modelfactory
from tests.contexts.publication.fixtures.sample_metadata import ArticleScenario
from tests.fundingrequests.test_doi_import_preview import (
    get_session_key,
    save_doi_import,
    submit_for_preview,
)


@pytest.fixture
def scenario() -> Generator[ArticleScenario]:
    """Inject fake DOI client into views via dependency injection."""
    scenario = ArticleScenario()
    DOIImportInputView.doi_client = scenario.client
    DOIPreviewDetailView.doi_client = scenario.client
    DOIPreviewSaveView.doi_client = scenario.client

    yield scenario

    DOIImportInputView.doi_client = crossref
    DOIPreviewDetailView.doi_client = crossref
    DOIPreviewSaveView.doi_client = crossref


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__previewing_doi_import_with_funding__shows_funding_on_preview_page(
    client: Client, scenario: ArticleScenario
) -> None:
    scenario = scenario.with_funding([("BMBF", "Some project", None)]).setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    preview_url = response["Location"]

    preview_response = client.get(preview_url)

    assert "BMBF" in preview_response.content.decode()
    assert "Some project" in preview_response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__previewing_doi_import_with_funding__delete_funding_entry__funding_is_gone(
    client: Client, scenario: ArticleScenario
) -> None:
    scenario = scenario.with_funding([("BMBF", "Some project", None)]).setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    key = get_session_key(response)

    delete_funding(client, key, DeleteFunding(funder="BMBF", project_id="Some project"))

    preview_url = response["Location"]
    preview = client.get(preview_url)
    assert "BMBF" not in preview.content.decode()
    assert "Some project" not in preview.content.decode()


NO_FUNDING_MESSAGE = "No funding information available."


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_funding__adds_new_funding_to_preview(
    client: Client, scenario: ArticleScenario
) -> None:
    """Adding a funding entry via HTMX endpoint shows it on the preview page."""
    funder = modelfactory.funding_organization(name="DFG")
    scenario = scenario.setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    key = get_session_key(response)

    add_funding(client, key, AddFunding(funder_id=funder.pk, project_id="PAK-999"))

    preview_url = response["Location"]
    preview = client.get(preview_url)
    content = preview.content.decode()
    assert NO_FUNDING_MESSAGE not in content
    assert "PAK-999" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_funding__preserves_existing_and_removed_funding(
    client: Client, scenario: ArticleScenario
) -> None:
    """Adding funding preserves original entries and respects prior removals."""
    funder = modelfactory.funding_organization(name="New Funder")
    scenario = scenario.with_funding([("BMBF", "old-project", None)]).setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    key = get_session_key(response)

    delete_funding(client, key, DeleteFunding(funder="BMBF", project_id="old-project"))
    add_funding(client, key, AddFunding(funder_id=funder.pk, project_id="new-project"))

    preview_url = response["Location"]
    preview = client.get(preview_url)
    content = preview.content.decode()
    assert "old-project" not in content
    assert "new-project" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__add_funding__then_delete__funding_is_gone(
    client: Client, scenario: ArticleScenario
) -> None:
    """Adding then deleting a funding entry removes it from the preview."""
    funder = modelfactory.funding_organization(name="Temp Funder")
    scenario = scenario.setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    key = get_session_key(response)

    add_funding(client, key, AddFunding(funder_id=funder.pk, project_id="temp-project"))

    preview_url = response["Location"]
    preview = client.get(preview_url)
    content = preview.content.decode()
    assert NO_FUNDING_MESSAGE not in content
    assert "temp-project" in content

    delete_funding(client, key, DeleteFunding(funder=funder.name, project_id="temp-project"))

    preview = client.get(preview_url)
    content = preview.content.decode()
    assert NO_FUNDING_MESSAGE in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reset_funding__restores_removed_funding_on_preview(
    client: Client, scenario: ArticleScenario
) -> None:
    """Reset funding restores originally detected funding entries that were removed."""
    scenario = scenario.with_funding([("BMBF", "original-project", None)]).setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    key = get_session_key(response)

    delete_funding(client, key, DeleteFunding(funder="BMBF", project_id="original-project"))
    reset_funding(client, key)

    preview_url = response["Location"]
    preview = client.get(preview_url)
    content = preview.content.decode()
    assert "original-project" in content
    assert NO_FUNDING_MESSAGE not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reset_funding__removes_added_funding_from_preview(
    client: Client, scenario: ArticleScenario
) -> None:
    """Reset funding removes user-added funding entries."""
    funder = modelfactory.funding_organization(name="Added Funder")
    scenario = scenario.setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    key = get_session_key(response)

    add_funding(client, key, AddFunding(funder_id=funder.pk, project_id="added-project"))
    reset_funding(client, key)

    preview_url = response["Location"]
    preview = client.get(preview_url)
    content = preview.content.decode()
    assert "added-project" not in content
    assert NO_FUNDING_MESSAGE in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reset_funding__preserves_publication_type_override(
    client: Client, scenario: ArticleScenario
) -> None:
    """Reset funding does not clear the publication type override."""
    publisher = modelfactory.publisher(name="Test Publisher")
    scenario = scenario.with_funding([("BMBF", "original-project", None)]).setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    key = get_session_key(response)

    override_to_monograph(client, key, PublisherId(publisher.pk))
    delete_funding(client, key, DeleteFunding(funder="BMBF", project_id="original-project"))
    reset_funding(client, key)

    preview_url = response["Location"]
    preview = client.get(preview_url)
    content = preview.content.decode()

    assert "original-project" in content
    assert "Monograph" in content or "monograph" in content


def delete_funding(client: Client, key: str, funding: DeleteFunding) -> None:
    client.post(
        reverse("fundingrequests:doi_preview_delete_funding", kwargs={"session_key": key}),
        formdata.map_to_dict(funding),
    )


def add_funding(client: Client, key: str, funding: AddFunding) -> None:
    client.post(
        reverse("fundingrequests:doi_preview_add_funding", kwargs={"session_key": key}),
        formdata.map_to_dict(funding),
    )


def reset_funding(client: Client, key: str) -> None:
    client.post(
        reverse("fundingrequests:doi_preview_reset_funding", kwargs={"session_key": key}),
    )


def override_to_monograph(client: Client, key: str, publisher: PublisherId) -> None:
    client.post(
        reverse("fundingrequests:doi_preview_apply_type_change", kwargs={"session_key": key}),
        data={"publication_type": "monograph", "publisher": publisher},
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__existing_funder__shows_existing_badge(client: Client, scenario: ArticleScenario) -> None:
    """Funder that already exists in the DB should show an 'Existing' badge."""
    modelfactory.funding_organization(name="BMBF")
    scenario = scenario.with_funding([("BMBF", "project-1", None)]).setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    preview = client.get(response["Location"])

    content = preview.content.decode()
    assert "BMBF" in content
    assert "Existing" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__new_funder__shows_new_badge(client: Client, scenario: ArticleScenario) -> None:
    """Funder that does NOT exist in the DB should show a 'New' badge."""
    scenario = scenario.with_funding([("NewFunder", "project-2", None)]).setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    preview = client.get(response["Location"])

    content = preview.content.decode()
    assert "NewFunder" in content
    assert "New" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__mixed_funders__shows_correct_badges(client: Client, scenario: ArticleScenario) -> None:
    """Mixed existing and new funders should show the correct badge for each."""
    modelfactory.funding_organization(name="DFG")
    scenario = scenario.with_funding(
        [("BMBF", "proj-a", None), ("DFG", "proj-b", None)]
    ).setup_client()
    response = submit_for_preview(client, scenario.doi.value())
    preview = client.get(response["Location"])

    content = preview.content.decode()
    # BMBF is new → "New" badge
    assert "New" in content
    # DFG exists → "Existing" badge
    assert "Existing" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__doi_import__matches_funder_by_doi_not_name(
    client: Client, scenario: ArticleScenario
) -> None:
    """Funder matched by DOI even if name differs."""
    existing_org = FundingOrganization.objects.create(name="Some Org")
    FundingOrganizationLink.objects.create(
        type=FundingOrganizationLinkType.objects.get(name="DOI"),
        value="10.13039/501100002347",
        funding_organization=existing_org,
    )

    scenario = (
        scenario.with_funding([("BMBF", "project-1", None)])
        .with_funder_doi("BMBF", "10.13039/501100002347")
        .setup_client()
    )
    response = submit_for_preview(client, scenario.doi.value())
    preview = client.get(response["Location"])
    content = preview.content.decode()

    assert "Existing" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__doi_import__creates_doi_link_on_name_matched_funder(
    client: Client, scenario: ArticleScenario
) -> None:
    """Name-matched funder gets a DOI link for future matches."""
    scenario = (
        scenario.with_funding([("BMBF", "project-1", None)])
        .with_funder_doi("BMBF", "10.13039/501100002347")
        .setup_client()
        .setup_db()
    )
    response = submit_for_preview(client, scenario.doi.value())
    key = get_session_key(response)
    save_doi_import(client, key)

    org = FundingOrganization.objects.get(name="BMBF")
    link = org.links.get()
    assert link.type.name == "DOI"
    assert link.value == "10.13039/501100002347"
