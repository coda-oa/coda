from coda.apps.fundingrequests.views.creationwizard import FundingRequestCreationWizard
from coda.apps.fundingrequests.views.wizard.steps.funding_step import FundingStep
from coda.apps.fundingrequests.views.wizard.parse_store import publication_dto_from
from coda.apps.fundingrequests.views.wizard.steps.journal_step import JournalStep
from coda.apps.fundingrequests.views.wizard.steps.publication_step import PublicationStep
from coda.apps.fundingrequests.views.wizard.steps.contact_step import (
    ExtraContactStep,
)
from coda.apps.wizard import SessionStore, Store
from coda.publication import Publication


class ArticleRequestWizard(FundingRequestCreationWizard[Publication]):
    store_name = "funding_request_wizard"
    store_factory = SessionStore
    steps = [JournalStep(), PublicationStep.for_article(), FundingStep(), ExtraContactStep()]

    def parse_publication(self, store: Store) -> Publication:
        publication = publication_dto_from(store).to_publication()
        return publication
