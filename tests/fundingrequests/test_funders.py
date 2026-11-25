import pytest
from django.contrib.messages import get_messages
from django.test.client import Client
from django.urls import reverse

from coda.apps.fundingrequests.forms import FundingOrganizationLinkForm
from coda.apps.fundingrequests.models import FundingOrganization
from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId, Doi


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


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_funder__redirects_to_detail_and_flashes_named_success(client: Client) -> None:
    response = client.post(reverse("fundingrequests:funders_create"), {"name": "BMBF"})

    org = FundingOrganization.objects.get(name="BMBF")
    assert response.status_code == 302
    assert response["Location"] == reverse("fundingrequests:funder_detail", kwargs={"pk": org.pk})
    assert [str(m) for m in get_messages(response.wsgi_request)] == [
        "Funding organization 'BMBF' created successfully."
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__update_funder__redirects_to_detail_and_flashes_named_success(client: Client) -> None:
    org = FundingOrganization.objects.create(name="Old Name")

    response = client.post(
        reverse("fundingrequests:funders_update", kwargs={"pk": org.pk}), {"name": "New Name"}
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("fundingrequests:funder_detail", kwargs={"pk": org.pk})
    assert [str(m) for m in get_messages(response.wsgi_request)] == [
        "Funding organization 'New Name' updated successfully."
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_list__searches_link_values(client: Client) -> None:
    org = FundingOrganization.objects.create(name="DFG")
    org.set_links([Ror("https://ror.org/04aj4c181")])

    response = client.get(reverse("fundingrequests:funders"), {"query": "04aj4c181"})

    assert "DFG" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_list__detects_bare_doi(client: Client) -> None:
    org = FundingOrganization.objects.create(name="BMBF")
    org.set_links([Doi("10.13039/501100002347")])

    response = client.get(reverse("fundingrequests:funders"), {"query": "10.13039/501100002347"})

    assert "BMBF" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
@pytest.mark.parametrize(
    "query",
    ["02mhbdp94", "https://ror.org/02mhbdp94", "https://ror.org/02mhbdp94/"],
)
def test__funder_list__detects_bare_and_url_ror(client: Client, query: str) -> None:
    org = FundingOrganization.objects.create(name="ROR Funder")
    org.set_links([Ror("https://ror.org/02mhbdp94")])

    response = client.get(reverse("fundingrequests:funders"), {"query": query})

    assert "ROR Funder" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_list__numeric_ror_shaped_token_stays_generic(client: Client) -> None:
    org = FundingOrganization.objects.create(name="Numeric ROR Funder")
    org.set_links([Ror("https://ror.org/000000195")])

    response = client.get(reverse("fundingrequests:funders"), {"query": "000000195"})

    assert "Numeric ROR Funder" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_list__mixed_link_prefixes_match_separate_rows(client: Client) -> None:
    matching = FundingOrganization.objects.create(name="Matching Funder")
    matching.set_links([Doi("10.1234/matching"), Ror("https://ror.org/02mhbdp94")])
    other = FundingOrganization.objects.create(name="Other Funder")
    other.set_links([Doi("10.1234/matching"), Ror("https://ror.org/04aj4c181")])

    response = client.get(
        reverse("fundingrequests:funders"),
        {"query": "doi:10.1234/matching ror:02mhbdp94"},
    )

    content = response.content.decode()
    assert "Matching Funder" in content
    assert "Other Funder" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_list__mixed_prefixes_and_generic_word(client: Client) -> None:
    matching = FundingOrganization.objects.create(name="Matching Springer Funder")
    matching.set_links([Doi("10.1234/matching"), Ror("https://ror.org/02mhbdp94")])

    response = client.get(
        reverse("fundingrequests:funders"),
        {"query": "doi:10.1234/matching ror:02mhbdp94 Springer"},
    )

    assert "Matching Springer Funder" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_list__crossref_prefix(client: Client) -> None:
    org = FundingOrganization.objects.create(name="Crossref Funder")
    org.set_links([CrossrefId("501100002347")])

    response = client.get(reverse("fundingrequests:funders"), {"query": "crossref:501100002347"})

    assert "Crossref Funder" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_list__multiple_matching_links__lists_funder_once(client: Client) -> None:
    org = FundingOrganization.objects.create(name="Duplicated Funder")
    org.set_links([CrossrefId("12345"), Doi("10.1234/123")])

    response = client.get(reverse("fundingrequests:funders"), {"query": "123"})

    assert [entity.name for entity in response.context["entities"]] == ["Duplicated Funder"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funder_list__renders_search_prefix_helper(client: Client) -> None:
    response = client.get(reverse("fundingrequests:funders"))

    content = response.content.decode()
    assert 'aria-describedby="entity-filter-helper"' in content
    assert "<code>name, doi, ror, crossref</code>" in content
