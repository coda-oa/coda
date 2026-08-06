from coda.domain.publication.links import Doi
from tests.contexts.fundingrequest.fixtures.protocols import ImportScenario
import pytest
from tests import modelfactory
from tests.contexts.fundingrequest.fixtures.sample_metadata import ArticleScenario, BookScenario

from coda.contexts.fundingrequest.dto.preview import PreviewExternalFunding
from coda.contexts.fundingrequest.services.doi_import._service import (
    DOIImportService,
    OverrideFunding,
    OverrideImport,
)
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.publication import JournalId


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
        PreviewExternalFunding(name="BMBF", identifiers=["10.0000/0000"], project_id="my-project"),
        PreviewExternalFunding(name=funder.name, project_id=project_id),
    ]
    assert result.publication.funding == expected


def test__override_import__reset_funding__clears_added_and_removed_funding() -> None:
    """reset_funding clears both added funding and removed-funding markers."""
    override = (
        OverrideImport.empty()
        .add_funding([OverrideFunding(FundingOrganizationId(1), "added-project")])
        .remove_funding("Existing Funder", "removed-project")
    )

    result = override.reset_funding()

    assert result._funding is None
    assert result._removed_funding == frozenset()


def test__override_import__reset_funding__preserves_publication_type_override() -> None:
    """reset_funding keeps the journal/publisher override intact."""
    override = OverrideImport.as_article(JournalId(42)).add_funding(
        [OverrideFunding(FundingOrganizationId(1), "added-project")]
    )

    result = override.reset_funding()

    assert result._journal_id == JournalId(42)
    assert result._publisher_id is None
    assert result._funding is None


@pytest.mark.django_db
@pytest.mark.parametrize("scenario", (ArticleScenario(), BookScenario()))
def test__reset_funding__restores_original_funding_in_preview(
    scenario: ArticleScenario | BookScenario,
) -> None:
    """After add+remove+reset, preview contains only the original detected funding."""
    funder = modelfactory.funding_organization()
    scenario = scenario.with_funding([("BMBF", "original-project", None)]).setup_client()

    service = DOIImportService(scenario.client)
    override = (
        OverrideImport.empty()
        .remove_funding("BMBF", "original-project")
        .add_funding([OverrideFunding(FundingOrganizationId(funder.pk), "added-project")])
        .reset_funding()
    )

    result = service.preview_with_override(scenario.doi, override)

    expected = [PreviewExternalFunding(name="BMBF", project_id="original-project")]
    assert result.publication.funding == expected
