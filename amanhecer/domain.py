"""Entidades e validação independentes de rede e interface."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import re
import unicodedata


class QueryKind(str, Enum):
    USERNAME = "arroba"
    CPF = "cpf"
    NAME = "nome"
    CNPJ = "cnpj"
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
    if kind == QueryKind.CPF:
        if not re.fullmatch(r"(?:[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2})", value):
            raise ValueError("Informe um CPF com 11 dígitos, com ou sem a pontuação padrão.")
        value = value.replace(".", "").replace("-", "")
        if len(set(value)) == 1:
            raise ValueError("Dígitos verificadores do CPF inválidos.")
        base = value[:9]
        for start in (10, 11):
            remainder = sum(int(char) * weight for char, weight in zip(base, range(start, 1, -1))) % 11
            base += str(0 if remainder < 2 else 11 - remainder)
        if value != base:
            raise ValueError("Dígitos verificadores do CPF inválidos.")
        return value
    if kind == QueryKind.NAME:
        value = unicodedata.normalize("NFC", value)
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("O nome não pode conter caracteres de controle.")
        value = " ".join(value.split())
        if (not 3 <= len(value) <= 120 or len(value.split()) < 2
                or any(not (char.isalpha() or char in " '-’") for char in value)
                or any(not any(char.isalpha() for char in part) for part in value.split())):
            raise ValueError("Informe o nome completo, com pelo menos duas palavras, usando letras, espaços, apóstrofos ou hífens.")
        return value
    if kind == QueryKind.USERNAME:
        value = value.removeprefix("@")
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}", value):
            raise ValueError("Informe apenas o arroba: de 1 a 64 letras ASCII, números, pontos, hífens ou sublinhados, com @ opcional.")
        return value
    if kind == QueryKind.DOMAIN:
        try:
            value = value.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("Domínio inválido.") from exc
        labels = value.split(".")
        if (len(value) > 253 or len(labels) < 2 or labels[-1].isdigit()
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels)):
            raise ValueError("Informe um domínio sem protocolo, porta ou caminho.")
        return value
    value = re.sub(r"[. /-]", "", value).upper()
    if kind == QueryKind.CNPJ:
        if not re.fullmatch(r"[A-Z0-9]{12}[0-9]{2}", value) or len(set(value)) == 1:
            raise ValueError("CNPJ deve ter 12 caracteres de base e 2 dígitos verificadores.")
        base = value[:12]
        for weights in ((5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2), (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)):
            remainder = sum((ord(c) - 48) * w for c, w in zip(base, weights)) % 11
            base += str(0 if remainder < 2 else 11 - remainder)
        if value != base:
            raise ValueError("Dígitos verificadores do CNPJ inválidos.")
    else:
        size = {QueryKind.CEP: 8, QueryKind.DDD: 2, QueryKind.BANK: 3}[kind]
        if not re.fullmatch(rf"[0-9]{{{size}}}", value):
            raise ValueError(f"{kind.value.upper()} deve conter {size} dígitos.")
    return value


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
    status: str
    data: Any = None
    error: str | None = None
    collected_at: str = field(default_factory=utc_now)


@dataclass
class Report:
    query: Query
    results: list[Evidence]
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["query"]["value"] = display_query(self.query)
        return result
