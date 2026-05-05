from typing import Any

from pydantic import Field, field_validator

from clashctl.models.base import ClashModel
from clashctl.models.enums import LogLevel


class LogLine(ClashModel):
    level: LogLevel = Field(alias="type")
    payload: str

    @field_validator("level", mode="before")
    @classmethod
    def _coerce_level(cls, v: Any) -> Any:
        # Pydantic's JSON-parsing fast path skips Enum._missing_, so we
        # normalize the alternate "warn" spelling and any unknown value here.
        if isinstance(v, str):
            return LogLevel(v)
        return v
