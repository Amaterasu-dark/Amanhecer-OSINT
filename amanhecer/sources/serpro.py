"""Validação local e adaptador para o serviço contratado Consulta CPF v3."""
from datetime import date
import re

from ..core.models import Evidence, Query, QueryKind
from ..core.contracts import AuthorizedJsonClient, SourceError, SourceHttpError


SERPRO_BASE = "https://gateway.apiserpro.serpro.gov.br/consulta-cpf-df/v3"


def birth_date(value: str) -> str:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Informe --nascimento no formato AAAA-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Data de nascimento inválida.") from exc
    if parsed > date.today():
        raise ValueError("A data de nascimento não pode estar no futuro.")
    return f"{parsed.day:02d}{parsed.month:02d}{parsed.year:04d}"


class SerproCpfProvider:
    name = "Serpro Consulta CPF v3"

    def __init__(self, client: AuthorizedJsonClient, token: str, birth: str):
        if not token or any(ord(char) < 33 or ord(char) > 126 for char in token):
            raise ValueError("Defina AMANHECER_SERPRO_TOKEN com um Bearer token válido do serviço contratado.")
        self.client = client
        self._token = token
        self.birth = birth_date(birth)

    def supports(self, query: Query) -> bool:
        return query.kind == QueryKind.CPF

    def collect(self, query: Query) -> Evidence:
        url = f"{SERPRO_BASE}/cpf/{query.value}/{self.birth}"
        # O relatório registra o endpoint, sem repetir CPF ou nascimento na URL.
        source = SERPRO_BASE + "/cpf/{ni}/{nasc}"
        data = {"match": "inconclusive", "check_digits_valid": True}
        try:
            response = self.client.get_response(url, bearer_token=self._token)
            payload = response.data
            if response.status_code not in (200, 206) or not isinstance(payload, dict):
                raise SourceError("Formato inesperado na resposta do Serpro.")
            if payload.get("ni") != query.value or payload.get("nascimento") != self.birth:
                raise SourceError("A resposta não confirmou o CPF e a data de nascimento informados.")
            record = {}
            if "nome" in payload:
                if not isinstance(payload["nome"], str) or not payload["nome"].strip():
                    raise SourceError("Nome cadastral inesperado na resposta do Serpro.")
                record["name"] = payload["nome"]
            if "situacao" in payload:
                status = payload["situacao"]
                if not isinstance(status, dict) or not all(isinstance(status.get(key), str) and status[key] for key in ("codigo", "descricao")):
                    raise SourceError("Situação cadastral inesperada na resposta do Serpro.")
                record.update(registration_status=status["descricao"], registration_status_code=status["codigo"])
            if response.status_code == 200 and ("name" not in record or "registration_status" not in record):
                raise SourceError("Resposta cadastral incompleta sem indicação de conteúdo parcial.")
            data.update(match="found", record=record, partial=response.status_code == 206,
                        detail="Conteúdo parcial retornado pela fonte." if response.status_code == 206 else "Consulta cadastral concluída no Serpro.")
            return Evidence(self.name, source, "ok", data=data)
        except SourceHttpError as exc:
            if exc.status_code == 404:
                data.update(match="not_found", detail="Nenhum cadastro retornado pela fonte para os dados informados.")
                return Evidence(self.name, source, "ok", data=data)
            messages = {
                400: "CPF ou data de nascimento rejeitados pela fonte.",
                401: "Token do Serpro ausente, expirado ou rejeitado; renove AMANHECER_SERPRO_TOKEN.",
                403: "Acesso ao serviço negado; confira a habilitação do contrato.",
                422: "A fonte não permitiu concluir a consulta com os dados informados.",
                451: "Consulta indisponível por restrição da fonte.",
            }
            return Evidence(self.name, source, "error", data=data, error=messages.get(exc.status_code, f"Falha HTTP {exc.status_code} na fonte de CPF."))
        except SourceError:
            return Evidence(self.name, source, "error", data=data,
                            error="A consulta ao Serpro falhou ou a resposta não confirmou os dados informados.")
