"""Regras puras de formato e normalização, sem rede ou adaptadores."""
import re
import unicodedata
from collections.abc import Sequence


BRAZIL_DIALING_PREFIX = "+55"
BRAZIL_COUNTRY_CODE = BRAZIL_DIALING_PREFIX.removeprefix("+")
DDD_LENGTH = 2
MOBILE_NUMBER_LENGTH = 9

DDDS = frozenset(
    "11 12 13 14 15 16 17 18 19 21 22 24 27 28 31 32 33 34 35 37 38 "
    "41 42 43 44 45 46 47 48 49 51 53 54 55 61 62 63 64 65 66 67 68 69 "
    "71 73 74 75 77 79 81 82 83 84 85 86 87 88 89 91 92 93 94 95 96 97 98 99".split()
)
CPF_WEIGHTS = (tuple(range(10, 1, -1)), tuple(range(11, 1, -1)))
CNPJ_WEIGHTS = (
    (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2),
    (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2),
)


def append_check_digits(base: str, weight_groups: Sequence[Sequence[int]]) -> str:
    """Calcula módulo 11 para CPF e CNPJ, inclusive base alfanumérica."""
    for weights in weight_groups:
        remainder = sum((ord(char) - ord("0")) * weight for char, weight in zip(base, weights)) % 11
        base += str(0 if remainder < 2 else 11 - remainder)
    return base


def normalize_phone(value: str) -> str:
    # O DDI sem '+' só é removido quando o comprimento elimina a ambiguidade com DDD 55.
    if value.startswith(BRAZIL_DIALING_PREFIX):
        value = value.removeprefix(BRAZIL_DIALING_PREFIX).lstrip(" ")
    elif re.fullmatch(re.escape(BRAZIL_COUNTRY_CODE) + r"[0-9]{10,11}", value):
        value = value.removeprefix(BRAZIL_COUNTRY_CODE)
    match = re.fullmatch(r"(?:\(([0-9]{2})\)|([0-9]{2})) ?([0-9]{4,5})-?([0-9]{4})", value)
    if not match:
        raise ValueError("Informe telefone brasileiro com DDD, como (11) 91234-5678 ou +5511912345678; sem ramal ou código de operadora.")
    ddd = match[1] or match[2]
    number = match[3] + match[4]
    if ddd not in DDDS:
        raise ValueError("DDD brasileiro inválido.")
    if not (re.fullmatch(r"9[0-9]{8}", number) or re.fullmatch(r"[2-6][0-9]{7}", number)):
        raise ValueError("Formato não suportado: use celular de 9 dígitos iniciado em 9 ou telefone fixo de 8 dígitos iniciado em 2 a 6.")
    return BRAZIL_DIALING_PREFIX + ddd + number


def normalize_cpf(value: str) -> str:
    if not re.fullmatch(r"(?:[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2})", value):
        raise ValueError("Informe um CPF com 11 dígitos, com ou sem a pontuação padrão.")
    value = value.replace(".", "").replace("-", "")
    if len(set(value)) == 1:
        raise ValueError("Dígitos verificadores do CPF inválidos.")
    if value != append_check_digits(value[:9], CPF_WEIGHTS):
        raise ValueError("Dígitos verificadores do CPF inválidos.")
    return value


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("O nome não pode conter caracteres de controle.")
    value = " ".join(value.split())
    if (not 3 <= len(value) <= 120 or len(value.split()) < 2
            or any(not (char.isalpha() or char in " '-’") for char in value)
            or any(not any(char.isalpha() for char in part) for part in value.split())):
        raise ValueError("Informe o nome completo, com pelo menos duas palavras, usando letras, espaços, apóstrofos ou hífens.")
    return value


def normalize_username(value: str) -> str:
    value = value.removeprefix("@")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}", value):
        raise ValueError("Informe apenas o arroba: de 1 a 64 letras ASCII, números, pontos, hífens ou sublinhados, com @ opcional.")
    return value


def normalize_domain(value: str) -> str:
    try:
        value = value.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("Domínio inválido.") from exc
    labels = value.split(".")
    if (len(value) > 253 or len(labels) < 2 or labels[-1].isdigit()
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels)):
        raise ValueError("Informe um domínio sem protocolo, porta ou caminho.")
    return value


def normalize_cnpj(value: str) -> str:
    if not re.fullmatch(r"(?:[A-Za-z0-9]{12}[0-9]{2}|[A-Za-z0-9]{2}\.[A-Za-z0-9]{3}\.[A-Za-z0-9]{3}/[A-Za-z0-9]{4}-[0-9]{2})", value):
        raise ValueError("Informe um CNPJ com 14 caracteres, com ou sem a pontuação padrão.")
    value = re.sub(r"[. /-]", "", value).upper()
    if not re.fullmatch(r"[A-Z0-9]{12}[0-9]{2}", value) or len(set(value)) == 1:
        raise ValueError("CNPJ deve ter 12 caracteres de base e 2 dígitos verificadores.")
    if value != append_check_digits(value[:12], CNPJ_WEIGHTS):
        raise ValueError("Dígitos verificadores do CNPJ inválidos.")
    return value


def normalize_numeric_code(value: str, size: int, label: str) -> str:
    value = re.sub(r"[. /-]", "", value).upper()
    if not re.fullmatch(rf"[0-9]{{{size}}}", value):
        raise ValueError(f"{label} deve conter {size} dígitos.")
    return value
