from collections.abc import Iterable
from typing import Any, Protocol, TypeVar, cast


from coda.apps.invoices import mapper as invoice_mapper
from coda.apps.invoices.models import FundingSource as FundingSourceModel
from coda.domain.author import InstitutionId
from coda.domain.finance.funding_sources import Budget, FundingSource, SplitSource
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.string import NonEmptyStr

K = TypeVar("K")  # Lookup key type
T = TypeVar("T", Budget, SplitSource)  # Source type


class FundingSourceStrategy(Protocol):
    """
    Protocol defining the strategy interface for funding source bulk creation.

    Each funding source type (Budget, Institution, etc.) implements this protocol
    to provide type-specific operations and configuration.
    """

    type_name: str
    """Database type discriminator value (e.g., "budget", "institution")"""

    filter_field: str
    """Field name for filtering and uniqueness checks (e.g., "name", "institution_id")"""

    @staticmethod
    def extract_source_key(source: Any) -> Any:
        """Extract the lookup key from a domain source object."""
        ...

    @staticmethod
    def extract_model_key(model: FundingSourceModel) -> Any:
        """Extract the lookup key from a database model instance."""
        ...

    @staticmethod
    def build_model(source: Any) -> FundingSourceModel:
        """Build a database model instance from a domain source object."""
        ...


class FundingSourceNotFound(ValueError):
    def __init__(self, id: int | None = None, name: str = "") -> None:
        if id:
            msg = f"FundingSource with {id=} does not exist"
        elif name:
            msg = f"FundingSource with {name=} does not exist"
        else:
            msg = "FundingSource not found"

        super().__init__(msg)


def get_by_id(id: FundingSourceId) -> FundingSource:
    try:
        model = FundingSourceModel.objects.get(pk=id)
    except FundingSourceModel.DoesNotExist as e:
        raise FundingSourceNotFound(id) from e

    return invoice_mapper.as_domain_funding_source(model)


def get_by_institution(id: InstitutionId) -> SplitSource:
    try:
        model = FundingSourceModel.objects.get(institution_id=id)
    except FundingSourceModel.DoesNotExist as e:
        raise FundingSourceNotFound(id) from e

    return SplitSource(FundingSourceId(model.pk), id, NonEmptyStr(model.name))


def get_by_name(name: str) -> FundingSource:
    try:
        model = FundingSourceModel.objects.get(name=name)
    except FundingSourceModel.DoesNotExist as e:
        raise FundingSourceNotFound(name=name) from e

    return invoice_mapper.as_domain_funding_source(model)


def create(source: FundingSource) -> FundingSourceId:
    if isinstance(source, Budget):
        type = "budget"
        institution_id = None
    elif isinstance(source, SplitSource):
        type = "institution"
        institution_id = source.institution
        existing = FundingSourceModel.objects.filter(institution_id=source.institution).first()
        if existing:
            return FundingSourceId(existing.pk)

    model = FundingSourceModel.objects.create(
        type=type, name=source.name, institution_id=institution_id
    )
    return FundingSourceId(model.pk)


class BudgetStrategy:
    """Strategy for Budget funding source bulk creation operations."""

    type_name = "budget"
    filter_field = "name"

    @staticmethod
    def extract_source_key(source: Budget) -> str:
        """Extract the lookup key (name) from a Budget."""
        return source.name

    @staticmethod
    def extract_model_key(model: FundingSourceModel) -> str:
        """Extract the lookup key (name) from a FundingSourceModel."""
        return model.name

    @staticmethod
    def build_model(source: Budget) -> FundingSourceModel:
        """Build a FundingSourceModel instance for a Budget."""
        return FundingSourceModel(type="budget", name=source.name)


class InstitutionStrategy:
    """Strategy for institution-based funding source bulk creation operations."""

    type_name = "institution"
    filter_field = "institution_id"

    @staticmethod
    def extract_source_key(source: SplitSource) -> InstitutionId:
        """Extract the lookup key (institution_id) from a SplitSource."""
        return source.institution

    @staticmethod
    def extract_model_key(model: FundingSourceModel) -> InstitutionId:
        """Extract the lookup key (institution_id) from a FundingSourceModel."""
        return cast(
            InstitutionId, model.institution_id
        )  # pyright: ignore[reportAttributeAccessIssue]

    @staticmethod
    def build_model(source: SplitSource) -> FundingSourceModel:
        """Build a FundingSourceModel instance for a SplitSource."""
        return FundingSourceModel(
            type="institution",
            name=source.name,
            institution_id=source.institution,
        )


def _bulk_create_deduplicated(
    indexed_items: list[tuple[int, T]],
    result: list[FundingSourceId | None],
    strategy: type[FundingSourceStrategy],
) -> None:
    """
    Generic bulk creation with deduplication for funding sources.

    This function implements the Strategy pattern to handle bulk creation
    of different funding source types with a unified algorithm:
    1. Query for existing entities
    2. Create only missing ones with bulk_create
    3. Handle conflicts from concurrent creates
    4. Populate result array at correct indices

    Args:
        indexed_items: List of (index, source) tuples maintaining original order
        result: Result array to populate with FundingSourceIds
        strategy: Strategy class providing type-specific operations and configuration
    """
    # Extract keys for querying
    keys: list[Any] = [strategy.extract_source_key(item) for _, item in indexed_items]

    # Query existing entities
    filter_kwargs = {"type": strategy.type_name, f"{strategy.filter_field}__in": keys}
    existing = FundingSourceModel.objects.filter(**filter_kwargs)
    existing_by_key: dict[Any, FundingSourceModel] = {
        strategy.extract_model_key(model): model for model in existing
    }

    # Identify items that need to be created
    to_create = [
        (idx, item)
        for idx, item in indexed_items
        if strategy.extract_source_key(item) not in existing_by_key
    ]

    # Bulk create missing items
    if to_create:
        models = [strategy.build_model(item) for _, item in to_create]
        created = FundingSourceModel.objects.bulk_create(models, ignore_conflicts=True)

        # Separate successful creates from conflicts
        with_pk = [m for m in created if m.pk]
        without_pk = [m for m in created if not m.pk]

        # Add successful creates to lookup
        existing_by_key.update({strategy.extract_model_key(m): m for m in with_pk})

        # Handle conflicts by refetching
        if without_pk:
            conflict_keys: list[Any] = [strategy.extract_model_key(m) for m in without_pk]
            refetch_kwargs = {
                "type": strategy.type_name,
                f"{strategy.filter_field}__in": conflict_keys,
            }
            refetched = FundingSourceModel.objects.filter(**refetch_kwargs)
            existing_by_key.update({strategy.extract_model_key(m): m for m in refetched})

    # Populate result array at correct indices
    for idx, item in indexed_items:
        model = existing_by_key[strategy.extract_source_key(item)]
        result[idx] = FundingSourceId(model.pk)


def create_many(sources: Iterable[FundingSource]) -> list[FundingSourceId]:
    """
    Create multiple funding sources in bulk, maintaining input order.

    Handles both Budget and SplitSource types. Returns existing IDs where
    funding sources already exist (budgets by name, institutions by institution_id).

    Args:
        sources: List of Budget or SplitSource domain objects

    Returns:
        List of FundingSourceIds in same order as input
    """
    sources_list = list(sources)
    if not sources_list:
        return []

    # Separate by type with their original indices
    budgets = [(i, s) for i, s in enumerate(sources_list) if isinstance(s, Budget)]
    institutions = [(i, s) for i, s in enumerate(sources_list) if isinstance(s, SplitSource)]

    # Initialize result array (will be filled by index)
    result: list[FundingSourceId | None] = [None] * len(sources_list)

    if budgets:
        _create_budgets(budgets, result)

    if institutions:
        _create_institutions(institutions, result)

    if any(id is None for id in result):
        raise ValueError("Failed to create some funding sources")

    return cast(list[FundingSourceId], result)


def _create_budgets(
    indexed_budgets: list[tuple[int, Budget]],
    result: list[FundingSourceId | None],
) -> None:
    """Create or get budgets and populate result at correct indices."""
    _bulk_create_deduplicated(indexed_budgets, result, BudgetStrategy)


def _create_institutions(
    indexed_institutions: list[tuple[int, SplitSource]],
    result: list[FundingSourceId | None],
) -> None:
    """Create or get institution funding sources and populate result at correct indices."""
    _bulk_create_deduplicated(indexed_institutions, result, InstitutionStrategy)
