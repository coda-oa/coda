from coda.domain.publication.links import Doi
from tests.contexts.publication.fixtures.protocols import ImportScenario
import pytest
from tests import modelfactory
from tests.contexts.publication.fixtures.sample_metadata import ArticleScenario, BookScenario

from coda.contexts.publication.dto.preview import PreviewExternalFunding
from coda.contexts.publication.services.doi_import_service import (
    DOIImportService,
    OverrideFunding,
    OverrideImport,
)
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId


@pytest.mark.django_db
@pytest.mark.parametrize("scenario", (ArticleScenario(), BookScenario()))
def test__previewing_article_without_funding__override_funding__saves_request_with_selected_funding(
    scenario: ImportScenario,
) -> None:
    scenario = scenario.setup_db()
    first_funder = modelfactory.funding_organization()
    first_project_id = "my-project"
    second_funder = modelfactory.funding_organization()
    second_project_id = "another-project"

    service = DOIImportService(doi_client=scenario.client)
    result = service.preview_with_override(
        scenario.doi,
        OverrideImport().add_funding(
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


@pytest.mark.django_db
@pytest.mark.parametrize("scenario", (ArticleScenario(), BookScenario()))
def test__previewing_article_with_funding__remove_funding__saves_without_funding(
    scenario: ArticleScenario | BookScenario,
) -> None:
    scenario = scenario.with_funding([("BMBF", "my-project", None)]).setup_client()

    service = DOIImportService(scenario.client)
    result = service.preview_with_override(
        scenario.doi, OverrideImport().remove_funding("BMBF", "my-project")
    )

    assert result.publication.funding == []


@pytest.mark.django_db
@pytest.mark.parametrize("scenario", (ArticleScenario(), BookScenario()))
def test__previewing_publication_with_funding__no_funding_override__keeps_original_funding(
    scenario: ArticleScenario | BookScenario,
) -> None:
    scenario = scenario.with_funding([("BMBF", "my-project", None)]).setup_client()

    service = DOIImportService(scenario.client)
    result = service.preview_with_override(scenario.doi)

    expected = [PreviewExternalFunding(name="BMBF", project_id="my-project")]
    assert result.publication.funding == expected


@pytest.mark.django_db
@pytest.mark.parametrize("scenario", (ArticleScenario(), BookScenario()))
def test__previewing_publication_with_funding__add_funding__saves_keeps_original_and_extra_funding(
    scenario: ArticleScenario | BookScenario,
) -> None:
    funder = modelfactory.funding_organization()
    project_id = "my-project"
    scenario = scenario.with_funding([("BMBF", "my-project", Doi("10.0000/0000"))]).setup_client()

    service = DOIImportService(scenario.client)
    result = service.preview_with_override(
        scenario.doi,
        OverrideImport().add_funding(
            [
                OverrideFunding(FundingOrganizationId(funder.pk), project_id),
            ]
        ),
    )

    expected = [
        PreviewExternalFunding(name="BMBF", project_id="my-project"),
        PreviewExternalFunding(name=funder.name, project_id=project_id),
    ]
    assert result.publication.funding == expected
