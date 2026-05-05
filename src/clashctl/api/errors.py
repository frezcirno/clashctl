class ClashError(Exception):
    """Base error for the Clash API client."""


class AuthError(ClashError):
    """401/403 from the Clash controller (bad or missing secret)."""


class NotFoundError(ClashError):
    """404 from the Clash controller."""


class HTTPStatusError(ClashError):
    """Non-2xx response that doesn't fit a more specific subclass."""

    def __init__(self, status_code: int, message: str = "") -> None:
        super().__init__(
            f"HTTP {status_code}: {message}" if message else f"HTTP {status_code}"
        )
        self.status_code = status_code


class StreamError(ClashError):
    """Streaming endpoint disconnected or produced unparseable data."""
