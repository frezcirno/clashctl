from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ClashModel(BaseModel):
    """Base for Clash API models. Most endpoints use camelCase JSON keys."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
    )


def _to_kebab(name: str) -> str:
    return name.replace("_", "-")


class ClashKebabModel(BaseModel):
    """Base for endpoints using kebab-case (notably `/configs`)."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=_to_kebab,
    )
