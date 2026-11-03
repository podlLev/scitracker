class SourceError(Exception):
    """An external source failed (network, HTTP status, malformed payload)."""

    def __init__(self, source: str, message: str) -> None:
        super().__init__(f"{source}: {message}")
        self.source = source
