from typing import Any

from pydantic import Field, field_validator

from clashctl.models.base import ClashKebabModel
from clashctl.models.enums import LogLevel, Mode


class ClashConfig(ClashKebabModel):
    """Mirror of Clash's `/configs` payload (kebab-case keys)."""

    port: int = 0
    socks_port: int = 0
    redir_port: int = 0
    tproxy_port: int = 0
    mixed_port: int = 0
    allow_lan: bool = False
    ipv6: bool = False
    mode: Mode = Mode.Rule
    log_level: LogLevel = LogLevel.Info
    bind_address: str = ""
    authentication: list[str] = Field(default_factory=list)

    @field_validator("mode", mode="before")
    @classmethod
    def _coerce_mode(cls, v: Any) -> Any:
        return Mode(v) if isinstance(v, str) else v

    @field_validator("log_level", mode="before")
    @classmethod
    def _coerce_log_level(cls, v: Any) -> Any:
        return LogLevel(v) if isinstance(v, str) else v

    @field_validator("authentication", mode="before")
    @classmethod
    def _coerce_authentication(cls, v: Any) -> Any:
        return [] if v is None else v
