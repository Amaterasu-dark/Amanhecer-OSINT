"""Validação do contrato HTTP e composição do caso de uso."""
import os

from ..core.models import Query, QueryKind
from ..core.service import InvestigationService
from ..sources.brasilapi import CnpjProvider, PhoneRegionProvider
from ..sources.local import CpfValidationProvider, CnpjValidationProvider, PhoneValidationProvider
from ..sources.registry import name_providers, username_providers
from ..sources.serpro import SerproCpfProvider, birth_date
from ..transport.http import HttpClient


ROUTES = {f"/api/v1/{kind.value}": kind for kind in (
    QueryKind.USERNAME, QueryKind.NAME, QueryKind.CPF, QueryKind.CNPJ, QueryKind.PHONE
)}


class ConfigurationError(Exception):
    pass


class ConsultationController:
    def __init__(self, client_factory=HttpClient):
        self.client_factory = client_factory

    def consult(self, kind: QueryKind, body: dict) -> tuple[int, dict]:
        if not isinstance(body, dict):
            raise ValueError("O corpo deve ser um objeto JSON.")
        allowed = {"valor"}
        if kind in (QueryKind.USERNAME, QueryKind.NAME):
            allowed.add("plataformas")
        if kind == QueryKind.NAME:
            allowed.add("limite")
        if kind in (QueryKind.CPF, QueryKind.CNPJ, QueryKind.PHONE):
            allowed.add("somente_validar")
        if kind == QueryKind.CPF:
            allowed.add("nascimento")
        if body.keys() - allowed:
            raise ValueError("Campos desconhecidos ou incompatíveis com esta rota.")
        if not isinstance(body.get("valor"), str):
            raise ValueError("valor deve ser uma string.")
        query = Query(kind, body["valor"])
        local = body.get("somente_validar", False)
        if type(local) is not bool:
            raise ValueError("somente_validar deve ser booleano.")
        platforms = body.get("plataformas")
        if "plataformas" in body and (not isinstance(platforms, list) or not platforms
                or not all(isinstance(item, str) for item in platforms)):
            raise ValueError("plataformas deve ser uma lista não vazia de strings.")
        limit = body.get("limite", 10)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limite deve ser um inteiro entre 1 e 50.")
        match kind:
            case QueryKind.USERNAME:
                providers = username_providers(self.client_factory(), platforms)
            case QueryKind.NAME:
                providers = name_providers(self.client_factory(), platforms, limit)
            case QueryKind.CNPJ:
                providers = [CnpjValidationProvider()] if local else [CnpjProvider(self.client_factory())]
            case QueryKind.PHONE:
                providers = [PhoneValidationProvider()]
                if not local:
                    providers.append(PhoneRegionProvider(self.client_factory()))
            case QueryKind.CPF:
                if local:
                    if "nascimento" in body:
                        raise ValueError("Validação local não usa nascimento.")
                    providers = [CpfValidationProvider()]
                else:
                    birth = body.get("nascimento")
                    if not isinstance(birth, str):
                        raise ValueError("Informe nascimento no formato AAAA-MM-DD.")
                    birth_date(birth)
                    token = os.environ.get("AMANHECER_SERPRO_TOKEN", "")
                    if not token:
                        raise ConfigurationError("Configure AMANHECER_SERPRO_TOKEN no servidor.")
                    providers = [SerproCpfProvider(self.client_factory(retries=0), token, birth)]
            case _:
                raise ValueError("Consulta não disponível.")
        report = InvestigationService(providers).investigate(query)
        status = 502 if any(item.status == "error" for item in report.results) else 200
        return status, report.to_dict()
