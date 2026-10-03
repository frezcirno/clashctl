from typing import Optional

from clashctl.models.base import ClashModel


class Version(ClashModel):
    version: str
    premium: Optional[bool] = None
