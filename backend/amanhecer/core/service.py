"""Caso de uso independente de CLI e implementação HTTP."""
from collections.abc import Sequence
from .models import Evidence, Query, Report
from .contracts import Provider, SourceError


class InvestigationService:
    def __init__(self, providers: Sequence[Provider]):
        self.providers = tuple(providers)

    def investigate(self, query: Query) -> Report:
        selected = [provider for provider in self.providers if provider.supports(query)]
        if not selected:
            raise ValueError("Nenhuma fonte disponível para essa consulta.")
        results = []
        for provider in selected:
            try:
                result = provider.collect(query)
                if not isinstance(result, Evidence):
                    raise SourceError("A fonte não retornou uma evidência válida.")
                results.append(result.validated())
            except SourceError:
                # Fontes interpretam seus erros; esta borda preserva as demais
                # caso uma falha esperada escape do adaptador.
                results.append(Evidence(provider.name, "local:falha-da-fonte", "error",
                                        {"match": "inconclusive"}, "Não foi possível concluir a consulta nesta fonte."))
        return Report(query, results)
