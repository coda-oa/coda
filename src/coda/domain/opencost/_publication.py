from __future__ import annotations

from enum import Enum
from typing import Self

from pydantic import BaseModel, model_validator

from ._types import NonEmptyString
from ._institution import InstitutionType
from ._invoice import PublicationInvoiceType


class CoarPublicationType(Enum):
    cartographic_material = "cartographic material"
    map = "map"
    dataset = "dataset"
    aggregated_data = "aggregated data"
    clinical_trial_data = "clinical trial data"
    compiled_data = "compiled data"
    encoded_data = "encoded data"
    experimental_data = "experimental data"
    genomic_data = "genomic data"
    geospatial_data = "geospatial data"
    laboratory_notebook = "laboratory notebook"
    measurement_and_test_data = "measurement and test data"
    observational_data = "observational data"
    recorded_data = "recorded data"
    simulation_data = "simulation data"
    survey_data = "survey data"
    design = "design"
    industrial_design = "industrial design"
    layout_design = "layout design"
    image = "image"
    moving_image = "moving image"
    video = "video"
    still_image = "still image"
    interactive_resource = "interactive resource"
    website = "website"
    learning_object = "learning object"
    other = "other"
    patent = "patent"
    pct_application = "PCT application"
    design_patent = "design patent"
    plant_patent = "plant patent"
    plant_variety_protection = "plant variety protection"
    software_patent = "software patent"
    utility_model = "utility model"
    software = "software"
    research_software = "research software"
    source_code = "source code"
    sound = "sound"
    musical_composition = "musical composition"
    text = "text"
    annotation = "annotation"
    bibliography = "bibliography"
    blog_post = "blog post"
    book = "book"
    book_part = "book part"
    conference_output = "conference output"
    conference_paper_not_in_proceedings = "conference paper not in proceedings"
    conference_poster_not_in_proceedings = "conference poster not in proceedings"
    conference_presentation = "conference presentation"
    conference_proceedings = "conference proceedings"
    conference_paper = "conference paper"
    conference_poster = "conference poster"
    journal = "journal"
    editorial = "editorial"
    journal_article = "journal article"
    corrigendum = "corrigendum"
    data_paper = "data paper"
    research_article = "research article"
    review_article = "review article"
    software_paper = "software paper"
    letter_to_the_editor = "letter to the editor"
    lecture = "lecture"
    letter = "letter"
    magazine = "magazine"
    manuscript = "manuscript"
    musical_notation = "musical notation"
    newspaper = "newspaper"
    newspaper_article = "newspaper article"
    other_periodical = "other periodical"
    preprint = "preprint"
    report = "report"
    clinical_study = "clinical study"
    data_management_plan = "data management plan"
    memorandum = "memorandum"
    policy_report = "policy report"
    project_deliverable = "project deliverable"
    research_protocol = "research protocol"
    research_report = "research report"
    technical_report = "technical report"
    research_proposal = "research proposal"
    review = "review"
    book_review = "book review"
    commentary = "commentary"
    peer_review = "peer review"
    technical_documentation = "technical documentation"
    thesis = "thesis"
    bachelor_thesis = "bachelor thesis"
    doctoral_thesis = "doctoral thesis"
    master_thesis = "master thesis"
    transcription = "transcription"
    working_paper = "working paper"
    trademark = "trademark"
    workflow = "workflow"


class PublicationSecondaryIdTypeEnum(Enum):
    doi = "doi"
    handle = "handle"
    urn = "urn"
    isbn = "isbn"
    pmid = "pmid"
    pmc = "pmc"
    arxiv = "arxiv"
    oai = "oai"
    local = "local"


class PublicationSecondaryIdType(BaseModel):
    value: NonEmptyString
    type: PublicationSecondaryIdTypeEnum


class PublicationSecondaryIdentifiers(BaseModel):
    id: list[PublicationSecondaryIdType]


class BibliographicInformation(BaseModel):
    Title: NonEmptyString
    Publisher: NonEmptyString
    isPartOf: NonEmptyString


class PublicationPrimaryIdentifier(BaseModel):
    doi: NonEmptyString | None = None
    bibliographic_information: BibliographicInformation | None = None

    @model_validator(mode="after")
    def _exactly_one_of_doi_or_bibliographic_information(self) -> Self:
        if (self.doi is not None) == (self.bibliographic_information is not None):
            raise ValueError(
                "exactly one of 'doi' or 'bibliographic_information' must be set"
            )
        return self


class PartOfContractType(BaseModel):
    group_id: NonEmptyString | None = None
    primary_identifier: ContractPrimaryIdentifier


class PublicationCostDataType(BaseModel):
    invoice: list[PublicationInvoiceType] | None = None
    part_of_contract: PartOfContractType | None = None


class PublicationType(BaseModel):
    primary_identifier: PublicationPrimaryIdentifier
    secondary_identifiers: PublicationSecondaryIdentifiers | None = None
    institution: InstitutionType
    publication_type: CoarPublicationType
    external_costsplitting: bool | None = None
    cost_data: PublicationCostDataType


# Import after all models are defined to avoid circular import during module loading
# Then rebuild models that have forward references
from ._contract import ContractPrimaryIdentifier  # noqa: E402

PartOfContractType.model_rebuild()
PublicationCostDataType.model_rebuild()
PublicationType.model_rebuild()
