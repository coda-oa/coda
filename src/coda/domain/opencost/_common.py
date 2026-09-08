from ._contract import ContractType
from ._publication import PublicationType
from ._validators import EitherFieldMixin


class Data(EitherFieldMixin):
    either_fields = ("publication", "contract")
    publication: list[PublicationType] | None = None
    contract: list[ContractType] | None = None
