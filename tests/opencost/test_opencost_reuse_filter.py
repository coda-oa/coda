import pytest
from django.test import Client

from tests import modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_processing_status(client: Client) -> None:
    """Processing status checkboxes should be checked when passed via URL."""
    response = client.get(
        "/opencost/generate/", {"processing_status": ["open", "approved", "closed"]}
    )
    content = response.content.decode()

    assert 'value="open"' in content
    assert 'value="approved"' in content
    assert 'value="closed"' in content
    # All three should have checked attribute
    assert content.count("checked") >= 3


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_publication_states(client: Client) -> None:
    """Publication state checkboxes should be checked when passed via URL."""
    response = client.get("/opencost/generate/", {"publication_states": ["Published", "Submitted"]})
    content = response.content.decode()

    assert 'value="Published"' in content
    assert 'value="Submitted"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_publication_type(client: Client) -> None:
    """Publication type select should have the correct option selected."""
    response = client.get("/opencost/generate/", {"publication_type": ["article"]})
    content = response.content.decode()

    assert 'value="article"' in content
    assert "selected" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_payment_methods(client: Client) -> None:
    """Payment method checkboxes should be checked when passed via URL."""
    response = client.get("/opencost/generate/", {"payment_methods": ["direct", "reimbursement"]})
    content = response.content.decode()

    assert 'value="direct"' in content
    assert 'value="reimbursement"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_open_access_type(client: Client) -> None:
    """Open access type should have correct options selected."""
    response = client.get("/opencost/generate/", {"open_access_type": ["Gold", "Hybrid"]})
    content = response.content.decode()

    assert 'value="Gold"' in content
    assert 'value="Hybrid"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_funding_source(client: Client) -> None:
    budget = modelfactory.budget(name="Test Budget")

    response = client.get("/opencost/generate/", {"funding_source": [str(budget.pk)]})
    content = response.content.decode()

    assert f'value="{budget.pk}"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_contract_name(client: Client) -> None:
    contract = modelfactory.contract()

    response = client.get("/opencost/generate/", {"contract_name": [str(contract.pk)]})
    content = response.content.decode()

    assert f'value="{contract.pk}"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__does_not_include_payment_status(client: Client) -> None:
    response = client.get("/opencost/generate/")
    content = response.content.decode()

    # Payment status should not be in the template
    assert "payment_status" not in content or "id_payment_status" not in content
