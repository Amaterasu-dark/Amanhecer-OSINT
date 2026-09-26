"""Resultados de validação local, sem acesso a APIs."""
from ..core.models import Evidence, Query, QueryKind
from ..core.normalization import BRAZIL_DIALING_PREFIX, BRAZIL_COUNTRY_CODE, DDD_LENGTH, MOBILE_NUMBER_LENGTH


def phone_parts(query: Query) -> tuple[str, str]:
    """Separa DDD e número de uma consulta já normalizada pelo domínio."""
    national = query.value.removeprefix(BRAZIL_DIALING_PREFIX)
    return national[:DDD_LENGTH], national[DDD_LENGTH:]


class PhoneValidationProvider:
    name = "Análise local de telefone"

    def supports(self, query: Query) -> bool:
        return query.kind == QueryKind.PHONE

    def collect(self, query: Query) -> Evidence:
        ddd, number = phone_parts(query)
        return Evidence(self.name, "local:telefone-br-formato", "ok", {
            "match": "format_valid", "format_valid": True,
            "phone": {"country_code": BRAZIL_COUNTRY_CODE, "ddd": ddd,
                      "type": "celular" if len(number) == MOBILE_NUMBER_LENGTH else "fixo/SCM"},
            "detail": "Formato compatível. Não confirma linha ativa, titular, operadora ou localização atual.",
        })


class CpfValidationProvider:
    name = "Validação local de CPF"

    def supports(self, query: Query) -> bool:
        return query.kind == QueryKind.CPF

    def collect(self, query: Query) -> Evidence:
        return Evidence(self.name, "local:cpf-digitos-verificadores", "ok", {
            "match": "validated", "check_digits_valid": True,
            "detail": "Formato e dígitos verificadores válidos. Nenhuma base cadastral foi consultada; isto não confirma inscrição, titularidade ou situação do CPF.",
        })


class CnpjValidationProvider:
    name = "Validação local de CNPJ"

    def supports(self, query: Query) -> bool:
        return query.kind == QueryKind.CNPJ

    def collect(self, query: Query) -> Evidence:
        return Evidence(self.name, "local:cnpj-digitos-verificadores", "ok", {
            "match": "validated", "check_digits_valid": True,
            "detail": "Formato e dígitos válidos; não confirma inscrição ou situação cadastral.",
        })


