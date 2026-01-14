"""Entity creation and lookup logic for import.

Handles:
- Finding or creating institutions, publishers, contracts, etc.
- Building lookup tables for bulk operations
- Caching to avoid duplicate queries
"""

from coda.apps.contracts import mapper as contract_mapper
from coda.apps.contracts import repository as contract_repository
from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.institutions.models import Institution
from coda.apps.journals.models import Journal
from coda.apps.publications.repositories import vocabulary_repository
from coda.apps.publishers.models import Publisher
from coda.contexts.fundingrequest.dto.import_dtos import FundingRequestImportListDto
from coda.domain.contract import Contract
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import Vocabulary

from .types import ImportLookups


def build_entity_lookups(import_data: FundingRequestImportListDto) -> ImportLookups:
    """Build lookup tables for all entities referenced in import data.

    This pre-creates or finds entities to optimize bulk import.

    Order of operations:
    1. Collect all entity identifiers from import data
    2. Pre-fetch existing journals (to determine which publishers exist)
    3. Filter and create publishers (avoiding duplicates from existing journals)
    4. Build remaining lookups
    """
    # Extract unique identifiers from import data
    institution_names = _collect_institution_names(import_data)
    contract_names = _collect_contract_names(import_data)
    funder_names = _collect_funder_names(import_data)
    vocabulary_names = _collect_vocabulary_names(import_data)
    journal_eissns = _collect_journal_eissns(import_data)

    # Pre-fetch existing journals (needed to filter publishers)
    existing_journals = _fetch_existing_journals(journal_eissns)

    # Collect publisher names (excluding those from existing journals)
    publisher_names = _collect_publisher_names(import_data, existing_journals)

    # Build publisher lookup (creates missing publishers)
    publishers_lookup = _build_publisher_lookup(publisher_names)

    # Add publishers from existing journals to lookup
    # (so they're available for monographs that might use the same publisher)
    for journal in existing_journals.values():
        if journal.publisher and journal.publisher.name not in publishers_lookup:
            publishers_lookup[journal.publisher.name] = journal.publisher

    # Build journal lookup (uses pre-fetched journals + publisher lookup)
    journals_lookup = _build_journal_lookup(
        journal_eissns, import_data, publishers_lookup, existing_journals
    )

    return ImportLookups(
        funding_organizations=_build_funding_org_lookup(funder_names),
        contracts=_build_contract_lookup(contract_names),
        institutions=_build_institution_lookup(institution_names),
        vocabularies=_build_vocabulary_lookup(vocabulary_names),
        publishers=publishers_lookup,
        journals=journals_lookup,
    )


def _collect_institution_names(import_data: FundingRequestImportListDto) -> set[str]:
    """Extract all unique institution names from author affiliations."""
    return {
        author.affiliation
        for request in import_data.requests
        for author in request.publication.authors
        if author.affiliation
    }


def _collect_contract_names(import_data: FundingRequestImportListDto) -> set[str]:
    """Extract all unique contract names."""
    return {
        contract.name
        for request in import_data.requests
        for contract in request.publication.contracts
    }


def _collect_funder_names(import_data: FundingRequestImportListDto) -> set[str]:
    """Extract all unique funder organization names."""
    return {
        funding.funder for request in import_data.requests for funding in request.research_funding
    }


def _collect_vocabulary_names(import_data: FundingRequestImportListDto) -> set[str]:
    """Extract all unique vocabulary names from import data."""
    names = set()
    for request in import_data.requests:
        pub = request.publication
        if pub.publication_type.vocabulary_name:
            names.add(pub.publication_type.vocabulary_name)
        if pub.subject_area.vocabulary_name:
            names.add(pub.subject_area.vocabulary_name)
    return names


def _collect_publisher_names(
    import_data: FundingRequestImportListDto, existing_journals: dict[str, Journal]
) -> set[str]:
    """Extract publisher names that need to be created.

    For articles: Only collect publisher names from articles whose journals don't exist yet.
    For monographs: Collect all publisher names (they're always needed).

    This prevents creating unnecessary publishers when journals already exist with publishers.
    """
    publisher_names = set()

    for request in import_data.requests:
        pub = request.publication
        if not pub.publisher_name:
            continue

        if pub.kind == "article":
            # For articles: only collect if journal doesn't exist yet
            if pub.eissn and pub.eissn not in existing_journals:
                publisher_names.add(pub.publisher_name)
        else:
            # For monographs: always collect (publishers needed directly)
            publisher_names.add(pub.publisher_name)

    return publisher_names


def _collect_journal_eissns(import_data: FundingRequestImportListDto) -> set[str]:
    """Extract all unique journal EISSNs from import data (articles only)."""
    return {
        request.publication.eissn
        for request in import_data.requests
        if request.publication.kind == "article" and request.publication.eissn
    }


def _fetch_existing_journals(eissns: set[str]) -> dict[str, Journal]:
    """Fetch existing journals by EISSN with publishers pre-loaded.

    Returns dict mapping EISSN to Journal for efficient lookup.
    """
    if not eissns:
        return {}

    existing = Journal.objects.filter(eissn__in=eissns).select_related("publisher")
    return {j.eissn: j for j in existing}


def _build_funding_org_lookup(names: set[str]) -> dict[str, FundingOrganization]:
    """Get or create funding organizations, return lookup dict."""
    if not names:
        return {}

    existing_orgs = FundingOrganization.objects.filter(name__in=names).order_by("id")

    lookup: dict[str, FundingOrganization] = {}
    for org in existing_orgs:
        if org.name not in lookup:
            lookup[org.name] = org

    missing_names = names - lookup.keys()

    if missing_names:
        new_orgs = FundingOrganization.objects.bulk_create(
            [FundingOrganization(name=name) for name in missing_names]
        )
        lookup.update({org.name: org for org in new_orgs})

    return lookup


def _build_contract_lookup(names: set[str]) -> dict[str, Contract]:
    """Get or create contracts, return lookup dict."""
    if not names:
        return {}

    # Bulk fetch all existing contracts using direct query with ordering (1 query)
    # Order by id to ensure we get the first match when there are duplicates
    existing_models = ContractModel.objects.filter(name__in=names).order_by("id")
    existing_contracts = [contract_mapper.as_domain_object(model) for model in existing_models]

    # Build lookup - only keep first occurrence for each name
    lookup: dict[str, Contract] = {}
    for contract in existing_contracts:
        name_str = str(contract.name)
        if name_str not in lookup:
            lookup[name_str] = contract

    # Identify missing contracts
    missing_names = names - lookup.keys()

    # Bulk create missing contracts (1 query if needed)
    if missing_names:
        new_contracts = [Contract.new(name=NonEmptyStr(name)) for name in missing_names]
        created_contracts = contract_repository.create_many(new_contracts)
        lookup.update({str(contract.name): contract for contract in created_contracts})

    return lookup


def _build_institution_lookup(names: set[str]) -> dict[str, Institution]:
    """Get or create institutions, return lookup dict."""
    if not names:
        return {}

    # Order by id to ensure we get the first match when there are duplicates
    existing_insts = Institution.objects.filter(name__in=names).order_by("id")

    lookup: dict[str, Institution] = {}
    for inst in existing_insts:
        if inst.name not in lookup:
            lookup[inst.name] = inst

    missing_names = names - lookup.keys()

    if missing_names:
        new_insts = Institution.objects.bulk_create(
            [Institution(name=name) for name in missing_names]
        )
        lookup.update({inst.name: inst for inst in new_insts})

    return lookup


def _build_vocabulary_lookup(names: set[str]) -> dict[str, Vocabulary]:
    """Get vocabularies by name, return lookup dict.

    Note: Missing vocabularies are silently skipped here.
    Errors will be raised during parsing when the vocabulary is actually needed.
    """
    if not names:
        return {}

    lookup: dict[str, Vocabulary] = {}
    for name in names:
        try:
            lookup[name] = vocabulary_repository.newest_base_vocabulary_by_name(name)
        except vocabulary_repository.VocabularyNotFoundError:
            # Skip missing vocabularies - errors will be reported during parsing
            pass

    return lookup


def _build_publisher_lookup(names: set[str]) -> dict[str, Publisher]:
    """Get or create publishers by name, return lookup dict.

    This is the single place where publishers are created during import.
    Names should already be filtered to exclude publishers from existing journals.

    Note: Publishers from existing journals are added to the lookup separately
    in build_entity_lookups() after this function runs.
    """
    if not names:
        return {}

    # Fetch existing publishers with deterministic ordering
    existing = Publisher.objects.filter(name__in=names).order_by("id")

    # Use first match for duplicates
    lookup: dict[str, Publisher] = {}
    for publisher in existing:
        if publisher.name not in lookup:
            lookup[publisher.name] = publisher

    # Identify missing publishers
    missing_names = names - lookup.keys()

    # Bulk create missing publishers
    if missing_names:
        new_publishers = Publisher.objects.bulk_create(
            [Publisher(name=name) for name in missing_names]
        )
        # Add newly created publishers to lookup
        lookup.update({p.name: p for p in new_publishers})

    return lookup


def _build_journal_lookup(
    eissns: set[str],
    import_data: FundingRequestImportListDto,
    publishers: dict[str, Publisher],
    existing_journals: dict[str, Journal],
) -> dict[str, Journal]:
    """Build journal lookup using pre-fetched journals and publishers.

    Args:
        eissns: Set of journal EISSNs from import data
        import_data: Full import data (for metadata)
        publishers: Publisher lookup (already complete)
        existing_journals: Pre-fetched existing journals

    Returns:
        Dict mapping EISSN to Journal
    """
    if not eissns:
        return {}

    # Start with pre-fetched journals
    lookup = dict(existing_journals)  # Copy to avoid mutating input

    # Identify missing journals
    missing_eissns = eissns - lookup.keys()

    # Create missing journals (publishers already exist in lookup)
    if missing_eissns:
        # Build mapping: eissn -> (title, publisher_name) from import data
        journal_metadata = {}
        for request in import_data.requests:
            pub = request.publication
            if pub.kind == "article" and pub.eissn in missing_eissns:
                # Use first occurrence of each EISSN
                if pub.eissn not in journal_metadata:
                    journal_metadata[pub.eissn] = (pub.journal_name, pub.publisher_name)

        # Create journal models
        new_journals = []
        for eissn in missing_eissns:
            title, publisher_name = journal_metadata.get(eissn, ("Imported journal", "Unknown"))

            # Publisher must exist in lookup (created in _build_publisher_lookup)
            publisher = publishers[publisher_name]
            new_journals.append(Journal(title=title, eissn=eissn, publisher=publisher))

        if new_journals:
            created = Journal.objects.bulk_create(new_journals)
            lookup.update({j.eissn: j for j in created})

    return lookup
