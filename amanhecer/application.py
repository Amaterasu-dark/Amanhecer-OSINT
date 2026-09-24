"""Caso de uso independente de CLI e implementação HTTP."""
from collections.abc import Sequence
from .domain import Query, Report
from .ports import Provider


class InvestigationService:
    def __init__(self, providers: Sequence[Provider]):
        self.providers = providers

    def investigate(self, query: Query) -> Report:
        selected = [provider for provider in self.providers if provider.supports(query)]
        if not selected:
            raise ValueError("Nenhuma fonte disponível para essa consulta.")
        return Report(query, [provider.collect(query) for provider in selected])
