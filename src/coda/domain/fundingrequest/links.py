from coda.domain.institution.links import Ror
from coda.domain.publication.links import Doi

_LinkTypes = {t.type(): t for t in (Doi, Ror)}
_LoweredLinkTypes = {t_name.lower(): t for t_name, t in _LinkTypes.items()}


def create_link(link_type: str, link_value: str) -> Doi | Ror:
    constructor = _LoweredLinkTypes.get(link_type.lower())
    if not constructor:
        raise ValueError(f"Unknown link type: {link_type}")
    return constructor(link_value)
