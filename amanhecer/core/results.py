"""Contrato dos resultados e validação antes da apresentação."""
import math
from typing import Literal, NotRequired, TypedDict, cast


Match = Literal["found", "not_found", "inconclusive", "candidates", "validated", "format_valid", "region"]
MATCHES = frozenset({"found", "not_found", "inconclusive", "candidates", "validated", "format_valid", "region"})


class Candidate(TypedDict):
    username: str
    profile_url: str
    display_name: NotRequired[str]
    identity_confirmed: NotRequired[bool]


class Phone(TypedDict):
    country_code: str
    ddd: str
    type: str


class Region(TypedDict):
    ddd: str
    state: str
    cities: list[str]


class EvidenceData(TypedDict, total=False):
    match: Match
    profile: dict[str, str | int]
    candidates: list[Candidate]
    record: dict[str, str]
    phone: Phone
    region: Region
    username: str
    detail: str
    note: str
    more_results_possible: bool
    incomplete_results: bool
    partial: bool
    check_digits_valid: bool
    format_valid: bool
    limit: int
    total_reported: int


def validate_json(value: object) -> None:
    """Também permite campos JSON do legado, com profundidade limitada."""
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            raise ValueError("Resultado excessivamente aninhado.")
        if item is None or type(item) in (str, bool, int):
            continue
        if type(item) is float and math.isfinite(item):
            continue
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        else:
            raise ValueError("Resultado contém valores fora do contrato JSON.")


def text_fields(value: object, required: tuple[str, ...] = (), *, integers: bool = False) -> None:
    allowed = (str, int) if integers else (str,)
    if (not isinstance(value, dict)
            or any(type(item) not in allowed for item in value.values())
            or any(not isinstance(value.get(key), str) or not value[key].strip() for key in required)):
        raise ValueError("Campos inválidos no resultado da fonte.")


def validate_result(value: object) -> EvidenceData:
    if value is None:
        return {"match": "inconclusive"}
    if not isinstance(value, dict):
        raise ValueError("O resultado da fonte deve ser um objeto.")
    validate_json(value)
    match = value.get("match", "inconclusive")
    if not isinstance(match, str) or match not in MATCHES:
        raise ValueError("Classificação de resultado inválida.")
    for key in ("username", "detail", "note"):
        if key in value and not isinstance(value[key], str):
            raise ValueError("Texto inválido no resultado.")
    for key in ("more_results_possible", "incomplete_results", "partial", "check_digits_valid", "format_valid"):
        if key in value and type(value[key]) is not bool:
            raise ValueError("Indicador inválido no resultado.")
    for key in ("limit", "total_reported"):
        if key in value and (type(value[key]) is not int or value[key] < 0):
            raise ValueError("Contagem inválida no resultado.")
    if "profile" in value:
        text_fields(value["profile"], integers=True)
    if "record" in value:
        text_fields(value["record"])
    if "phone" in value:
        text_fields(value["phone"], ("country_code", "ddd", "type"))
    if "region" in value:
        region = value["region"]
        if not isinstance(region, dict) or not isinstance(region.get("cities"), list):
            raise ValueError("Região inválida no resultado.")
        text_fields({key: region.get(key) for key in ("ddd", "state")}, ("ddd", "state"))
        if any(not isinstance(city, str) or not city.strip() for city in region["cities"]):
            raise ValueError("Municípios inválidos no resultado.")
    if "candidates" in value:
        if not isinstance(value["candidates"], list):
            raise ValueError("Lista de candidatos inválida.")
        for candidate in value["candidates"]:
            if not isinstance(candidate, dict):
                raise ValueError("Candidato inválido.")
            text_fields({key: candidate.get(key) for key in ("username", "profile_url")}, ("username", "profile_url"))
            if "display_name" in candidate and not isinstance(candidate["display_name"], str):
                raise ValueError("Nome de candidato inválido.")
            if "identity_confirmed" in candidate and type(candidate["identity_confirmed"]) is not bool:
                raise ValueError("Indicador de identidade inválido.")
    required = {"candidates": "candidates", "region": "region", "format_valid": "phone"}.get(match)
    if required and required not in value:
        raise ValueError("Resultado sem os dados da classificação informada.")
    return cast(EvidenceData, {**value, "match": match})
