from clashctl.models.base import ClashModel


class Version(ClashModel):
    version: str
    premium: bool | None = None
