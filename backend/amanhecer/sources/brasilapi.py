"""Consultas de CNPJ e região de DDD na BrasilAPI."""
from ..core.models import Evidence, Query, QueryKind
from ..core.contracts import JsonClient, SourceError, SourceHttpError
from .local import phone_parts


STATES = frozenset("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


class CnpjProvider:
    name = "BrasilAPI CNPJ"

    def __init__(self, client: JsonClient):
        self.client = client

    def supports(self, query: Query) -> bool:
        return query.kind == QueryKind.CNPJ

    def parse(self, payload: object, query: Query) -> dict[str, str]:
        if not isinstance(payload, dict) or not isinstance(payload.get("cnpj"), str):
            raise SourceError("Formato inesperado na resposta de CNPJ.")
        try:
            returned = Query(QueryKind.CNPJ, payload["cnpj"])
        except ValueError as exc:
            raise SourceError("CNPJ inválido na resposta da fonte.") from exc
        if returned.value != query.value:
            raise SourceError("A fonte retornou um CNPJ diferente do consultado.")
        name = payload.get("razao_social")
        if not isinstance(name, str) or not name.strip():
            raise SourceError("Resposta sem razão social válida.")
        record = {"cnpj": query.value, "name": name}
        fields = {
            "nome_fantasia": "trade_name", "descricao_situacao_cadastral": "registration_status",
            "data_inicio_atividade": "started_at", "cnae_fiscal_descricao": "activity",
            "municipio": "city", "uf": "state", "logradouro": "street",
            "numero": "number", "complemento": "complement", "bairro": "district", "cep": "postal_code",
        }
        for source, target in fields.items():
            value = payload.get(source)
            if value is not None:
                if not isinstance(value, str):
                    raise SourceError(f"Campo empresarial inesperado: {source}.")
                record[target] = value
        return record

    def collect(self, query: Query) -> Evidence:
        url = f"https://brasilapi.com.br/api/cnpj/v1/{query.value}"
        data = {"match": "inconclusive", "check_digits_valid": True}
        try:
            payload = self.client.get(url)
            record = self.parse(payload, query)
            data.update(match="found", record=record,
                        detail="Cadastro retornado pela BrasilAPI; os dados podem estar desatualizados.")
            return Evidence(self.name, url, "ok", data)
        except SourceHttpError as exc:
            if exc.status_code == 404:
                data.update(match="not_found", detail="CNPJ não encontrado nesta fonte.")
                return Evidence(self.name, url, "ok", data)
            return Evidence(self.name, url, "error", data, error=str(exc))
        except SourceError as exc:
            return Evidence(self.name, url, "error", data, error=str(exc))


class PhoneRegionProvider:
    name = "BrasilAPI região do DDD"

    def __init__(self, client: JsonClient):
        self.client = client

    def supports(self, query: Query) -> bool:
        return query.kind == QueryKind.PHONE

    def collect(self, query: Query) -> Evidence:
        ddd, _ = phone_parts(query)
        url = f"https://brasilapi.com.br/api/ddd/v1/{ddd}"
        data = {"match": "inconclusive"}
        try:
            payload = self.client.get(url)
            if (not isinstance(payload, dict) or not isinstance(payload.get("state"), str)
                    or payload["state"] not in STATES or not isinstance(payload.get("cities"), list)
                    or not payload["cities"] or any(not isinstance(city, str) or not city.strip() for city in payload["cities"])):
                raise SourceError("Formato inesperado na resposta de DDD.")
            data.update(match="region", region={"ddd": ddd, "state": payload["state"], "cities": payload["cities"]},
                        detail="Região de numeração do DDD; não indica a localização atual do telefone. Somente o DDD foi enviado à fonte.")
            return Evidence(self.name, url, "ok", data)
        except SourceError as exc:
            return Evidence(self.name, url, "error", data, error=str(exc))
