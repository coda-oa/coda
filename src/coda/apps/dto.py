from typing import Any

from pydantic import BaseModel
from pydantic_core import to_jsonable_python


class CodaBaseDto(BaseModel):
    def to_post_data(self, exclude: set[str] | None = None) -> dict[str, Any]:
        return {
            k: to_jsonable_python(v) if v is not None else ""
            for k, v in self.model_dump(exclude=exclude).items()
        }
