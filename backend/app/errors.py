from __future__ import annotations


class RepositoryNotReadyError(RuntimeError):
    """Raised when an online operation has no configured runtime repository."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"MySQL runtime repository is unavailable for `{operation}`. "
            "Configure NEWSREC_DATABASE_URL and wait for readiness."
        )
        self.operation = operation


class UnresolvedQueryError(ValueError):
    """Raised when a search input cannot be mapped to a known query_key."""

    def __init__(self, query_input: str) -> None:
        super().__init__("No matching query found. Try a suggested query.")
        self.query_input = query_input


class SearchIndexNotReadyError(RuntimeError):
    """Raised when hybrid search is configured without compatible artifacts."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"Hybrid search index is unavailable: {detail}")
        self.detail = detail


class IdempotencyConflictError(ValueError):
    """Raised when one event ID is reused for different semantic payloads."""
