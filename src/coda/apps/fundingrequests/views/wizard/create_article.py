from coda.apps.fundingrequests.views.creationwizard import FundingRequestCreationWizard
from coda.apps.fundingrequests.views.wizard.parse_store import publication_dto_from
from coda.apps.fundingrequests.views.wizard.steps.extrainformation_step import ExtraInformationStep
from coda.apps.fundingrequests.views.wizard.steps.funding_step import FundingStep
from coda.apps.fundingrequests.views.wizard.steps.journal_step import JournalContractStep
from coda.apps.fundingrequests.views.wizard.steps.publication_step import PublicationStep
from coda.apps.publications.dto import PublicationDto
from coda.apps.wizard import SessionStore, Store
from coda.apps.breadcrumbs.decorators import breadcrumb


@breadcrumb("New Funding Request for an Article", parent_url_name="fundingrequests:list")
class ArticleRequestWizard(FundingRequestCreationWizard[PublicationDto]):
    store_name = "funding_request_wizard"
    store_factory = SessionStore
    steps = [
        JournalContractStep(),
        PublicationStep.for_article(),
        FundingStep(),
        ExtraInformationStep(),
    ]

    def parse_publication(self, store: Store) -> PublicationDto:
        return publication_dto_from(store)
