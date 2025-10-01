from coda.apps.fundingrequests.views.creationwizard import FundingRequestCreationWizard
from coda.apps.fundingrequests.views.wizard.parse_store import monograph_dto_from
from coda.apps.fundingrequests.views.wizard.steps.extrainformation_step import ExtraInformationStep
from coda.apps.fundingrequests.views.wizard.steps.funding_step import FundingStep
from coda.apps.fundingrequests.views.wizard.steps.publication_step import PublicationStep
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import PublisherStep
from coda.apps.publications.dto import MonographDto
from coda.apps.wizard import SessionStore, Store
from django.utils.decorators import method_decorator
from coda.apps.breadcrumbs.decorators import breadcrumb


@method_decorator(breadcrumb("New Funding Request for a Monograph", parent_url_name="fundingrequests:list"), name="dispatch")
class MonographRequestWizard(FundingRequestCreationWizard[MonographDto]):
    store_name = "monograph_request_wizard"
    store_factory = SessionStore
    steps = [
        PublisherStep(),
        PublicationStep.for_monograph(),
        FundingStep(),
        ExtraInformationStep(),
    ]

    def parse_publication(self, store: Store) -> MonographDto:
        publication = monograph_dto_from(store)
        return publication
