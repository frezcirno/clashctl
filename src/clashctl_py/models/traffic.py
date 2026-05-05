from clashctl_py.models.base import ClashModel


class Traffic(ClashModel):
    up: int = 0
    down: int = 0
