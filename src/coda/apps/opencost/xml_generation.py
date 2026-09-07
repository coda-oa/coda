from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET

from pydantic import BaseModel

if TYPE_CHECKING:
    from coda.apps.opencost.models import (
        OpenCostReport,
        OpenCostReportContract,
        OpenCostReportPublication,
    )

from coda.apps.opencost.transformers import to_opencost
from coda.domain.opencost import Data

NAMESPACE = "https://opencost.de"


def _text(value: object) -> str:
    """Format a scalar leaf as XML text.

    Every domain field ends up as one of these four kinds; anything else
    would silently render via ``str()`` and produce schema-invalid text.
    """
    if isinstance(value, Enum):
        # Members store their XSD wire string as value, e.g.
        # CoarPublicationType.journal_article -> "journal article".
        return str(value.value)
    if isinstance(value, bool):
        # xs:boolean literals; Python's default "True" would not parse.
        return "true" if value else "false"
    if isinstance(value, Decimal):
        # xs:decimal amounts: fixed two decimals, no float artifacts.
        return f"{value:.2f}"
    # NonEmptyString / Currency / DateFormat are validated plain strings.
    return str(value)


def _element(value: Any, name: str) -> ET.Element:  # noqa: ANN401
    """Render a domain model (or scalar) as an XML element named ``name``.

    The whole OpenCost XML shape is derived from the pydantic models
    themselves, so no per-type serialize functions are needed:

    - a ``BaseModel`` becomes an element whose children are its fields,
      in declaration order (``_elements`` maps each child value to the
      element(s) it contributes);
    - anything else becomes a text node, formatted by ``_text``.

    Declaration order makes the output *deterministic*, not schema-correct:
    the OpenCost XSD constrains these types with ``xs:all`` or with
    symmetric ``xs:choice`` branches that accept either child order
    (verified with xmllint against opencost.xsd). Nothing here may assume
    a child order is required.

    ``value`` is deliberately ``Any``: the recursion alternates between
    models and scalars and terminates at scalars. Lists only ever arrive
    through ``_elements`` (the schema has no nested lists).
    """
    elem = ET.Element(name)
    if isinstance(value, BaseModel):
        # model_fields preserves field declaration order (pydantic v2
        # guarantee); read via type() -- accessing it on instances is deprecated.
        for field_name, field in type(value).model_fields.items():
            # Attribute lookup uses the Python field name; the element name
            # below comes from the field's alias when one is defined.
            child = getattr(value, field_name)
            # None means "element absent" (XSD minOccurs=0). Required fields
            # are enforced non-None by pydantic, so omitting None children can
            # never drop schema-required content.
            if child is not None:
                # .alias doubles as the wire name for fields named after a
                # Python keyword or reserved word (from_ -> <from>). pydantic's
                # serialization_alias is NOT consulted here -- the models must
                # keep setting plain alias to influence the element name.
                elem.extend(_elements(child, field.alias or field_name))
    else:
        elem.text = _text(value)
    return elem


def _elements(value: Any, name: str) -> list[ET.Element]:  # noqa: ANN401
    """Map one field value to the element(s) it contributes under its parent.

    - ``list`` -> repeated sibling elements sharing the field name, the
      XSD ``maxOccurs="unbounded"`` pattern; an empty optional list simply
      emits nothing, which the surrounding minOccurs=0 particles accept.
    - wrapper elements the XSD models as plural-around-singular (e.g.
      ``amounts_paid`` around ``amount_paid``) are nested models
      (``PublicationAmountsPaid``), so a list never needs a wrapper here.
    - anything else -> exactly one element, delegated to ``_element``.
    """
    if isinstance(value, list):
        return [_element(item, name) for item in value]
    return [_element(value, name)]


def pydantic_to_xml(data: Data) -> str:
    root = _element(data, "data")
    root.set("xmlns", NAMESPACE)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def generate_xml(
    report: "OpenCostReport",
    publications: "list[OpenCostReportPublication] | None" = None,
    contracts: "list[OpenCostReportContract] | None" = None,
) -> str:
    data = to_opencost(report, publications, contracts)
    if data is None:
        # XSD requires at least one publication or contract — nothing to generate.
        return ""
    return pydantic_to_xml(data)
