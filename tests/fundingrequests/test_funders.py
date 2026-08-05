import pytest
from django.test.client import Client
from django.urls import reverse

from coda.apps.fundingrequests.forms import FundingOrganizationLinkForm
from coda.apps.fundingrequests.models import FundingOrganization
from coda.domain.institution.links import Ror
from coda.domain.publication.links import Doi


def assert_org_has_links(org: FundingOrganization, expected: list[Doi | Ror]) -> None:
    org.refresh_from_db()
    links = sorted(org.get_links(), key=lambda link: link.type())
    assert links == sorted(expected, key=lambda link: link.type())


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_funder_with_doi__persists_doi_link(client: Client) -> None:
    _ = client.post(
        reverse("fundingrequests:funders_create"),
        data={"name": "BMBF", "link_type": ["DOI"], "link_value": ["10.13039/501100002347"]},
    )
    org = FundingOrganization.objects.get(name="BMBF")
    link = org.links.get()
    assert link.type.name == "DOI"
    assert link.value == "10.13039/501100002347"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_funder_with_ror__persists_ror_link(client: Client) -> None:
    client.post(
        reverse("fundingrequests:funders_create"),
        data={
            "name": "DFG",
            "link_type": ["ROR"],
            "link_value": ["https://ror.org/04aj4c181"],
        },
    )
    org = FundingOrganization.objects.get(name="DFG")
    link = org.links.get()
    assert link.type.name == "ROR"
    assert link.value == "https://ror.org/04aj4c181"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_funder_replaces_links(client: Client) -> None:
    org = FundingOrganization.objects.create(name="BMBF")
    org.set_links([Doi("10.13039/old-doi")])

    client.post(
        reverse("fundingrequests:funders_update", kwargs={"pk": org.pk}),
        data={"name": "BMBF", "link_type": ["DOI"], "link_value": ["10.13039/new-doi"]},
    )

    assert_org_has_links(org, [Doi("10.13039/new-doi")])


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_funder_with_invalid_link__preserves_existing_links(client: Client) -> None:
    org = FundingOrganization.objects.create(name="BMBF")
    org.set_links([Doi("10.13039/501100002347")])

    response = client.post(
        reverse("fundingrequests:funders_update", kwargs={"pk": org.pk}),
        data={"name": "BMBF", "link_type": ["DOI"], "link_value": ["not-a-valid-doi"]},
    )

    assert_org_has_links(org, [Doi("10.13039/501100002347")])
    assert "not-a-valid-doi" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_funder_with_invalid_link__does_not_create_orphaned_org(
    client: Client,
) -> None:
    response = client.post(
        reverse("fundingrequests:funders_create"),
        data={"name": "OrphanOrg", "link_type": ["DOI"], "link_value": ["not-a-valid-doi"]},
    )
    assert not FundingOrganization.objects.filter(name="OrphanOrg").exists()
    assert response.status_code == 200
    assert "not-a-valid-doi" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_funder_with_multiple_links__persists_all(client: Client) -> None:
    client.post(
        reverse("fundingrequests:funders_create"),
        data={
            "name": "BMBF",
            "link_type": ["DOI", "ROR"],
            "link_value": ["10.13039/501100002347", "https://ror.org/04aj4c181"],
        },
    )
    org = FundingOrganization.objects.get(name="BMBF")
    assert_org_has_links(org, [Doi("10.13039/501100002347"), Ror("https://ror.org/04aj4c181")])


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_funder_with_multiple_links__replaces_all(client: Client) -> None:
    org = FundingOrganization.objects.create(name="BMBF")
    org.set_links([Doi("10.13039/old-doi")])

    client.post(
        reverse("fundingrequests:funders_update", kwargs={"pk": org.pk}),
        data={
            "name": "BMBF",
            "link_type": ["DOI", "ROR"],
            "link_value": ["10.13039/new-doi", "https://ror.org/04aj4c181"],
        },
    )

    assert_org_has_links(org, [Doi("10.13039/new-doi"), Ror("https://ror.org/04aj4c181")])


def test__link_form_with_valid_doi__returns_domain_link() -> None:
    form = FundingOrganizationLinkForm({"link_type": "DOI", "link_value": "10.13039/501100002347"})
    form.full_clean()
    link = form.link_object()
    assert link is not None
    assert link.type() == "DOI"
    assert link.value() == "10.13039/501100002347"


def test__link_form_with_valid_ror__returns_domain_link() -> None:
    form = FundingOrganizationLinkForm(
        {"link_type": "ROR", "link_value": "https://ror.org/04aj4c181"}
    )
    form.full_clean()
    link = form.link_object()
    assert link is not None
    assert link.type() == "ROR"
    assert link.value() == "https://ror.org/04aj4c181"


def test__link_form_with_invalid_value__link_object_returns_none() -> None:
    form = FundingOrganizationLinkForm({"link_type": "DOI", "link_value": "not-a-valid-doi"})
    form.full_clean()
    assert form.link_object() is None
    assert form.errors


def test__link_form_with_empty_data__link_object_returns_none() -> None:
    form = FundingOrganizationLinkForm({"link_type": "", "link_value": ""})
    form.full_clean()
    assert form.link_object() is None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_list__shows_identifier_tags(client: Client) -> None:
    org = FundingOrganization.objects.create(name="BMBF")
    org.set_links([Doi("10.13039/501100002347")])

    response = client.get(reverse("fundingrequests:funders"))
    content = response.content.decode()

    assert "BMBF" in content
    assert "10.13039/501100002347" in content
    assert "label" in content
    assert "pill" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__list_view__multi_word_search__each_word_matches_independently(
    client: Client,
) -> None:
    FundingOrganization.objects.create(name="Alpha Beta Gamma")

    response = client.get(reverse("fundingrequests:funders"), {"query": "Alpha Gamma"})

    assert response.status_code == 200
    assert "Alpha Beta Gamma" in response.content.decode()
