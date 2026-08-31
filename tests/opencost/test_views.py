import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.opencost.models import OpenCostReport


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invalid_open_access_type__generating_report__re_renders_without_creating(
    client: Client,
) -> None:
    response = client.post(
        reverse("opencost:generate_submit"),
        data={
            "title": "Broken Report",
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
            "open_access_type": ["bogus"],
        },
    )

    assert response.status_code == 200
    assert "form_errors" in response.context
    assert response.context["current_filters"]["open_access_type"] == ["bogus"]
    assert OpenCostReport.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__valid_minimal_generate_post__generating_report__creates_report(client: Client) -> None:
    response = client.post(
        reverse("opencost:generate_submit"),
        data={
            "title": "Valid Report",
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
        },
    )

    assert response.status_code == 302
    assert OpenCostReport.objects.get(title="Valid Report").filters == {
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
    }
