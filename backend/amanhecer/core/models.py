"""Entidades e validação independentes de rede e interface."""
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Literal
from .results import EvidenceData, validate_result
from .normalization import (
    normalize_cpf, normalize_cnpj, normalize_name, normalize_username,
    normalize_domain, normalize_phone, normalize_numeric_code,
)


class QueryKind(str, Enum):
    USERNAME = "arroba"
    CPF = "cpf"
    NAME = "nome"
    CNPJ = "cnpj"
    PHONE = "telefone"
    CEP = "cep"
    DDD = "ddd"
    BANK = "banco"
    DOMAIN = "dominio"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def display_query(query: "Query") -> str:
    return "***.***.***-" + query.value[-2:] if query.kind == QueryKind.CPF else query.value


def normalize(kind: QueryKind, value: str) -> str:
    value = value.strip()
    match kind:
        case QueryKind.PHONE:
            return normalize_phone(value)
        case QueryKind.CPF:
            return normalize_cpf(value)
        case QueryKind.CNPJ:
            return normalize_cnpj(value)
        case QueryKind.NAME:
            return normalize_name(value)
        case QueryKind.USERNAME:
            return normalize_username(value)
        case QueryKind.DOMAIN:
            return normalize_domain(value)
        case QueryKind.CEP:
            return normalize_numeric_code(value, 8, "CEP")
        case QueryKind.DDD:
            return normalize_numeric_code(value, 2, "DDD")
        case QueryKind.BANK:
            return normalize_numeric_code(value, 3, "BANCO")
        case _:
            raise ValueError("Tipo de consulta inválido.")


@dataclass(frozen=True)
class Query:
    kind: QueryKind
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", normalize(self.kind, self.value))


@dataclass
class Evidence:
    provider: str
    source_url: str
    status: Literal["ok", "error"]
    data: EvidenceData | None = None
    error: str | None = None
    collected_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        try:
            if self.status not in ("ok", "error"):
                raise ValueError("Status de resultado inválido.")
            self.data = validate_result(self.data)
        except ValueError:
            self.status = "error"
            self.data = {"match": "inconclusive"}
            self.error = "A fonte retornou dados incompatíveis com o formato do relatório."

    def validated(self) -> "Evidence":
        """Revalida alterações feitas após a criação, sem mudar o original."""
        return replace(self)


@dataclass
class Report:
    query: Query
    results: list[Evidence]
    created_at: str = field(default_factory=utc_now)

    def unique_results(self) -> list[Evidence]:
        """Preserva a primeira coleta de evidências iguais, sem ocultar divergências."""
        results, seen = [], set()
        for item in self.results:
            item = item.validated()
            key = (item.provider, item.source_url, item.status, item.error,
                   json.dumps(item.data, sort_keys=True, ensure_ascii=False))
            if key not in seen:
                seen.add(key)
                results.append(item)
        return results

    def __post_init__(self) -> None:
        self.results = self.unique_results()

    def to_dict(self) -> dict:
        result = asdict(replace(self, results=self.unique_results()))
        result["query"]["value"] = display_query(self.query)
        return result
