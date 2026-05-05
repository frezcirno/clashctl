from clashctl_py.models.base import ClashModel


class Version(ClashModel):
    version: str
    premium: bool | None = None
