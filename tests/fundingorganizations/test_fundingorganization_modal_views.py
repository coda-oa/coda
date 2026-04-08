import re

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests.models import FundingOrganization


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__click_on_new_funding_organization_from_funding_request__returns_modal_with_form_and_correct_context(
    client: Client,
) -> None:
    response = client.get(reverse("fundingrequests:funders_create_modal"))

    assert response.status_code == 200
    assert "partials/entity_creation_modal.html" in [t.name for t in response.templates]
    assert "form" in response.context
    assert response.context["entity_name"] == "Funding Organization"
    assert response.context["entity_create_url"] == "fundingrequests:funders_create_modal_submit"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__valid_funding_organization_entered__click_create_button__creates_organization_and_returns_success_template(
    client: Client,
) -> None:
    organization_name = "German Research Foundation"

    formset_data = {
        "name": organization_name,
        "total_forms": "0",
    }

    response = client.post(
        reverse("fundingrequests:funders_create_modal_submit"),
        formset_data,
    )

    assert FundingOrganization.objects.filter(name=organization_name).exists()
    organization = FundingOrganization.objects.get(name=organization_name)

    assert response.status_code == 200
    assert "fundingrequests/funders/funder_create_success.html" in [
        t.name for t in response.templates
    ]
    assert response.context["organization"] == organization

    content = response.content.decode()

    assert re.search(
        r'<div[^>]{0,200}id="entity-creation-modal-wrapper"[^>]{0,200}hx-swap-oob="true"', content
    )
    assert re.search(r'<div[^>]{0,200}id="funding-formset"[^>]{0,200}hx-swap-oob="true"', content)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invalid_funding_organization_entered__click_create_button__returns_modal_with_errors(
    client: Client,
) -> None:
    initial_count = FundingOrganization.objects.count()

    response = client.post(
        reverse("fundingrequests:funders_create_modal_submit"),
        {"name": ""},
    )

    assert FundingOrganization.objects.count() == initial_count  # No new organization created

    assert response.status_code == 200
    assert "partials/entity_creation_modal.html" in [t.name for t in response.templates]
    assert "form" in response.context
    assert response.context["form"].errors


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_funder_from_formset_modal__click_create_in_funder_modal__rebuilds_formset_row_with_user_data_and_new_funder_in_selects(
    client: Client,
) -> None:
    existing_org = FundingOrganization.objects.create(name="Existing Foundation")

    new_organization_name = "European Research Council"

    formset_data = {
        "name": new_organization_name,
        "total_forms": "2",
        "form-1-organization": str(existing_org.pk),
        "form-1-project_name": "My Research Project",
        "form-2-organization": "",
        "form-2-project_name": "",
    }

    response = client.post(
        reverse("fundingrequests:funders_create_modal_submit"),
        formset_data,
    )

    content = response.content.decode()

    assert re.search(r'<div[^>]{0,200}id="funding-formset"[^>]{0,200}hx-swap-oob="true"', content)

    assert "My Research Project" in content

    assert re.search(rf'<li[^>]{{0,200}}value="{existing_org.pk}"', content)
    assert re.search(rf"<li[^>]{{0,100}}>{{0,200}}{re.escape(new_organization_name)}</li>", content)
    assert re.search(rf"<li[^>]{{0,100}}>{{0,200}}{re.escape(existing_org.name)}</li>", content)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__create_funder_from_modal__click_create_from_funder_modal__preserves_existing_two_rows_of_user_input_in_external_funding_and_payment_information(
    client: Client,
) -> None:
    org1 = FundingOrganization.objects.create(name="Foundation One")
    org2 = FundingOrganization.objects.create(name="Foundation Two")

    new_org_name = "Swiss National Science Foundation"

    formset_data = {
        "name": new_org_name,
        "amount": "1000.0",
        "currency": "EUR",
        "method": "direct",
        "total_forms": "3",
        "form-1-organization": str(org1.pk),
        "form-1-project_id": "ABC-123",
        "form-1-project_name": "Project Alpha",
        "form-2-organization": str(org2.pk),
        "form-2-project_id": "DEF-456",
        "form-2-project_name": "Project Beta",
        "form-3-organization": "",
        "form-3-project_id": "",
        "form-3-project_name": "",
    }

    response = client.post(
        reverse("fundingrequests:funders_create_modal_submit"),
        formset_data,
    )

    content = response.content.decode()
    formset = response.context["funding_formset"]

    form1 = formset.forms[0]
    assert form1["organization"].value() in [org1.pk, str(org1.pk)]

    form2 = formset.forms[1]
    assert form2["organization"].value() in [org2.pk, str(org2.pk)]

    assert "Project Alpha" in content
    assert "Project Beta" in content
    assert "ABC-123" in content
    assert "DEF-456" in content

    assert re.search(rf"<li[^>]{{0,100}}>{{0,200}}{re.escape(org1.name)}</li>", content)
    assert re.search(rf"<li[^>]{{0,100}}>{{0,200}}{re.escape(org2.name)}</li>", content)
    assert re.search(rf"<li[^>]{{0,100}}>{{0,200}}{re.escape(new_org_name)}</li>", content)

    assert re.search(rf'<li[^>]{{0,200}}value="{org1.pk}"', content)
    assert re.search(rf'<li[^>]{{0,200}}value="{org2.pk}"', content)

    new_org = FundingOrganization.objects.get(name=new_org_name)
    assert re.search(rf'<li[^>]{{0,200}}value="{new_org.pk}"', content)
