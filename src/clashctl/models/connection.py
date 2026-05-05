from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from clashctl.models.base import ClashModel
from clashctl.models.enums import RuleType


class Metadata(ClashModel):
    connection_type: str = Field(alias="type")
    source_ip: str = Field(alias="sourceIP")
    source_port: str
    destination_ip: str = Field(alias="destinationIP")
    destination_port: str
    host: str
    network: str


class Connection(ClashModel):
    id: str
    upload: int
    download: int
    metadata: Metadata
    rule: RuleType
    rule_payload: str
    start: datetime
    chains: list[str] = Field(default_factory=list)

    @field_validator("rule", mode="before")
    @classmethod
    def _coerce_rule(cls, v: Any) -> Any:
        return RuleType(v) if isinstance(v, str) else v


class Connections(ClashModel):
    connections: list[Connection] = Field(default_factory=list)
    download_total: int = 0
    upload_total: int = 0

    @field_validator("connections", mode="before")
    @classmethod
    def _coerce_connections(cls, v: Any) -> Any:
        return [] if v is None else v
