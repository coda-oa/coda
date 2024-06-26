from pathlib import Path

from ._common import create_fixture
from .coar import parse_vocabulary as parse_coar
from .dfg_subject_classification import parse_vocabulary as parse_dfg


def export() -> None:
    coar = parse_coar()
    fixture_json = create_fixture(coar, vocabulary_pk=1, concept_pk_start=1)
    Path("config/fixtures/coar_resource_types_3_1.json").write_text(fixture_json)

    dfg = parse_dfg()
    fixture_json = create_fixture(dfg, vocabulary_pk=2, concept_pk_start=coar.total_concepts() + 1)
    Path("config/fixtures/dfg_subject_classification.json").write_text(fixture_json)


export()
