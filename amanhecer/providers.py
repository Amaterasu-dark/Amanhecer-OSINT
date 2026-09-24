"""Adaptadores de fontes públicas com procedência por resultado."""
from abc import ABC, abstractmethod
from urllib.parse import quote, urlencode
from .domain import Evidence, Query, QueryKind
from .ports import JsonClient, SourceError
from .usernames import username_providers


class RemoteProvider(ABC):
    def __init__(self, client: JsonClient, name: str):
        self.client, self.name = client, name

    @abstractmethod
    def supports(self, query: Query) -> bool: ...

    @abstractmethod
    def url(self, query: Query) -> str: ...

    def parse(self, payload, query: Query):
        if not isinstance(payload, dict) or not payload:
            raise SourceError("Formato inesperado na resposta da fonte.")
        return payload

    def collect(self, query: Query) -> Evidence:
        url = self.url(query)
        try:
            data = self.parse(self.client.get(url), query)
            return Evidence(self.name, url, "ok", data=data)
        except SourceError as exc:
            return Evidence(self.name, url, "error", error=str(exc))


class BrasilApiProvider(RemoteProvider):
    ROUTES = {QueryKind.CNPJ: "cnpj/v1", QueryKind.CEP: "cep/v2", QueryKind.DDD: "ddd/v1", QueryKind.BANK: "banks/v1", QueryKind.DOMAIN: "registrobr/v1"}

    def __init__(self, client: JsonClient):
        super().__init__(client, "BrasilAPI")

    def supports(self, query: Query) -> bool:
        return query.kind in self.ROUTES and (query.kind != QueryKind.DOMAIN or query.value.endswith(".br"))

    def url(self, query: Query) -> str:
        return f"https://brasilapi.com.br/api/{self.ROUTES[query.kind]}/{quote(query.value, safe='')}"


class DnsProvider(RemoteProvider):
    def __init__(self, client: JsonClient, record: str):
        super().__init__(client, f"Google DNS {record}")
        self.record = record

    def supports(self, query: Query) -> bool:
        return query.kind == QueryKind.DOMAIN

    def url(self, query: Query) -> str:
        return "https://dns.google/resolve?" + urlencode({"name": query.value, "type": self.record, "edns_client_subnet": "0.0.0.0/0"})

    def parse(self, payload, query: Query):
        payload = super().parse(payload, query)
        if payload.get("Status") not in (0, 3):
            raise SourceError(f"Falha DNS: código {payload.get('Status')}.")
        return {"status": payload["Status"], "nxdomain": payload["Status"] == 3, "answers": payload.get("Answer", []), "dnssec_validated": payload.get("AD", False)}


class CertificateProvider(RemoteProvider):
    def __init__(self, client: JsonClient):
        super().__init__(client, "crt.sh")

    def supports(self, query: Query) -> bool:
        return query.kind == QueryKind.DOMAIN

    def url(self, query: Query) -> str:
        return "https://crt.sh/?" + urlencode({"q": "%." + query.value, "output": "json"})

    def parse(self, payload, query: Query):
        if not isinstance(payload, list) or any(not isinstance(item, dict) or not isinstance(item.get("name_value"), str) for item in payload):
            raise SourceError("Formato inesperado no serviço de certificados.")
        names = set()
        for item in payload:
            for name in item["name_value"].splitlines():
                name = name.lower().removeprefix("*.").rstrip(".")
                if name == query.value or name.endswith("." + query.value):
                    names.add(name)
        return {"domains": sorted(names), "entries_received": len(payload), "note": "Certificados históricos não comprovam atividade ou propriedade atual."}


def legacy_providers(client: JsonClient) -> list[RemoteProvider]:
    """Fontes do protótipo anterior, fora da CLI focada em usuários."""
    return [BrasilApiProvider(client), *(DnsProvider(client, record) for record in ("A", "AAAA", "MX", "NS", "TXT", "CAA")), CertificateProvider(client)]


def default_providers(client: JsonClient, platforms: list[str] | None = None):
    return username_providers(client, platforms)
