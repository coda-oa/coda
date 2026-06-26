from tests import modelfactory
import pytest
from coda.contexts.publication.dto.preview import PreviewExternalFunding
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from tests.contexts.publication.fixtures.sample_metadata import ArticleScenario

from coda.contexts.publication.services.doi_import_service import (
    DOIImportService,
    OverrideFunding,
    OverrideImportFunding,
)


@pytest.mark.django_db
def test__previewing_article_without_funding__override_funding__saves_request_with_selected_funding() -> (
    None
):
    scenario = ArticleScenario().setup_db()
    first_funder = modelfactory.funding_organization()
    first_project_id = "my-project"
    second_funder = modelfactory.funding_organization()
    second_project_id = "another-project"

    service = DOIImportService(doi_client=scenario.client)
    result = service.build_preview_with_type_override(
        scenario.doi,
        funding_override=OverrideImportFunding(
            [
                OverrideFunding(FundingOrganizationId(first_funder.pk), first_project_id),
                OverrideFunding(FundingOrganizationId(second_funder.pk), second_project_id),
            ],
        ),
    )

    assert result.publication.funding == [
        PreviewExternalFunding(name=first_funder.name, project_id=first_project_id),
        PreviewExternalFunding(name=second_funder.name, project_id=second_project_id),
    ]
