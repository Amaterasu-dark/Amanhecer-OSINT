"""Contratos entre aplicação e adaptadores."""
from typing import Any, Protocol
from dataclasses import dataclass
from ..core.models import Evidence, Query


class SourceError(Exception):
    """Falha esperada de uma fonte externa."""


class SourceHttpError(SourceError):
    """Falha HTTP com código preservado para interpretação pelo provedor."""

    def __init__(self, status_code: int, message: str | None = None):
        self.status_code = status_code
        super().__init__(message or f"HTTP {status_code} recebido da fonte.")


class JsonClient(Protocol):
    def get(self, url: str) -> Any: ...


@dataclass(frozen=True)
class JsonResponse:
    status_code: int
    data: Any


class AuthorizedJsonClient(Protocol):
    def get_response(self, url: str, *, bearer_token: str | None = None) -> JsonResponse: ...


class Provider(Protocol):
    name: str

    def supports(self, query: Query) -> bool: ...
    def collect(self, query: Query) -> Evidence: ...
