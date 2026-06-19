import pytest
from django.test import Client

from tests import modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_processing_status(client: Client) -> None:
    response = client.get(
        "/exports/fundingrequests-csv/create/",
        {"processing_status": ["open", "approved", "closed"]},
    )
    content = response.content.decode()

    assert 'value="open"' in content
    assert 'value="approved"' in content
    assert 'value="closed"' in content
    # All three should have checked attribute
    assert content.count("checked") >= 3


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_multiple_publication_states(client: Client) -> None:
    response = client.get(
        "/exports/fundingrequests-csv/create/", {"publication_states": ["Published", "Submitted"]}
    )
    content = response.content.decode()

    # Parse the HTML to check both are checked
    # Find the checkbox for Published
    published_start = content.find('value="Published"')
    published_checked = content[published_start : published_start + 100].find("checked") != -1

    # Find the checkbox for Submitted
    submitted_start = content.find('value="Submitted"')
    submitted_checked = content[submitted_start : submitted_start + 100].find("checked") != -1

    assert published_checked, "Published should be checked"
    assert submitted_checked, "Submitted should be checked"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_publication_states(client: Client) -> None:
    response = client.get(
        "/exports/fundingrequests-csv/create/", {"publication_states": ["Published"]}
    )
    content = response.content.decode()

    assert 'value="Published"' in content
    assert "checked" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_publication_type(client: Client) -> None:
    response = client.get("/exports/fundingrequests-csv/create/", {"publication_type": ["article"]})
    content = response.content.decode()

    assert 'value="article"' in content
    assert "selected" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_payment_methods(client: Client) -> None:
    response = client.get(
        "/exports/fundingrequests-csv/create/", {"payment_methods": ["direct", "reimbursement"]}
    )
    content = response.content.decode()

    assert 'value="direct"' in content
    assert 'value="reimbursement"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_open_access_type(client: Client) -> None:
    response = client.get(
        "/exports/fundingrequests-csv/create/", {"open_access_type": ["Gold", "Hybrid"]}
    )
    content = response.content.decode()

    assert 'value="Gold"' in content
    assert 'value="Hybrid"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_payment_status(client: Client) -> None:
    response = client.get(
        "/exports/fundingrequests-csv/create/", {"payment_status": ["paid", "unpaid"]}
    )
    content = response.content.decode()

    assert 'value="paid"' in content
    assert 'value="unpaid"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_funding_source(client: Client) -> None:
    budget = modelfactory.budget(name="Test Budget")

    response = client.get(
        "/exports/fundingrequests-csv/create/", {"funding_source": [str(budget.pk)]}
    )
    content = response.content.decode()

    assert f'value="{budget.pk}"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__redo_button__prefills_contract_name(client: Client) -> None:
    contract = modelfactory.contract()

    response = client.get(
        "/exports/fundingrequests-csv/create/", {"contract_name": [str(contract.pk)]}
    )
    content = response.content.decode()

    assert f'value="{contract.pk}"' in content
