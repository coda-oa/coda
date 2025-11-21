from coda.apps.institutions import repository as institution_repository
from coda.apps.institutions.models import Institution
from coda.apps.invoices import funding_source_repository
from coda.domain.author import InstitutionId
from coda.domain.finance.funding_sources import Budget, FundingSource, SplitSource


def resolve_funding_source(funding_source: FundingSource) -> FundingSource:
    match funding_source:
        case Budget(id=int(id)):
            return funding_source_repository.get_by_id(id)
        case SplitSource(institution=institution):
            return _ensure_institution_source(institution)

    raise ValueError(f"Invalid {funding_source=}")


def _ensure_institution_source(id: InstitutionId) -> SplitSource:
    try:
        fs = funding_source_repository.get_by_institution(id)
    except funding_source_repository.FundingSourceNotFound:
        institution = _try_get_insitution(id)
        fs = SplitSource.new(id, institution.name)
        fs.id = funding_source_repository.create(fs)

    return fs


def _try_get_insitution(id: InstitutionId) -> Institution:
    try:
        institution = institution_repository.get_by_id(id)
    except Exception as e:
        print(e)
        raise ValueError(f"Institution with {id=} does not exist") from e

    return institution
