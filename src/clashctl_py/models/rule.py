from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import Field, field_validator

from clashctl_py.models.base import ClashModel
from clashctl_py.models.enums import RuleType


class Rule(ClashModel):
    rule_type: RuleType = Field(alias="type")
    payload: str
    proxy: str

    @field_validator("rule_type", mode="before")
    @classmethod
    def _coerce_rule_type(cls, v: Any) -> Any:
        return RuleType(v) if isinstance(v, str) else v


class Rules(ClashModel):
    rules: list[Rule] = Field(default_factory=list)

    @field_validator("rules", mode="before")
    @classmethod
    def _coerce_rules(cls, v: Any) -> Any:
        return [] if v is None else v

    def frequency(self) -> dict[str, int]:
        """Count proxy references in rules, excluding DIRECT/REJECT."""
        return Counter(
            r.proxy for r in self.rules if r.proxy not in {"DIRECT", "REJECT"}
        )

    def most_frequent_proxy(self) -> str | None:
        freq = self.frequency()
        return max(freq, key=freq.get) if freq else None  # type: ignore[arg-type]
