"""Pesquisa por nome em perfis públicos; resultados são candidatos, não identidades confirmadas."""
from abc import ABC, abstractmethod
from urllib.parse import quote, urlencode
import re

from .domain import Evidence, Query, QueryKind
from .ports import JsonClient, SourceError


NAME_NOTE = "Resultados de busca podem incluir homônimos ou correspondências aproximadas; a identidade não foi confirmada."


class NameProvider(ABC):
    name: str

    def __init__(self, client: JsonClient, limit: int = 10):
        if not 1 <= limit <= 50:
            raise ValueError("O limite de resultados deve estar entre 1 e 50.")
        self.client, self.limit = client, limit

    def supports(self, query: Query) -> bool:
        return query.kind == QueryKind.NAME

    @abstractmethod
    def url(self, query: Query) -> str: ...

    @abstractmethod
    def parse(self, payload) -> dict: ...

    def collect(self, query: Query) -> Evidence:
        url = self.url(query)
        try:
            data = self.parse(self.client.get(url))
            candidates = data["candidates"]
            incomplete = data.get("incomplete_results", False)
            data.update(match="candidates" if candidates else "inconclusive" if incomplete else "not_found",
                        note=NAME_NOTE, limit=self.limit,
                        detail=f"Busca limitada aos primeiros {self.limit} resultados por fonte.")
            return Evidence(self.name, url, "error" if incomplete else "ok", data=data,
                            error="A fonte informou que a pesquisa está incompleta." if incomplete else None)
        except SourceError as exc:
            return Evidence(self.name, url, "error", data={"match": "inconclusive", "note": NAME_NOTE}, error=str(exc))

    def candidates(self, items: list, username_field: str, base: str) -> list[dict]:
        if len(items) > self.limit:
            raise SourceError("A fonte excedeu o limite de resultados solicitado.")
        results, seen = [], set()
        for item in items:
            if not isinstance(item, dict):
                raise SourceError("Formato inesperado na busca por nome.")
            username = item.get(username_field)
            if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}", username):
                raise SourceError("Arroba inesperado no resultado de busca.")
            if username.casefold() in seen:
                continue
            seen.add(username.casefold())
            candidate = {"username": username, "profile_url": base + quote(username, safe=""), "identity_confirmed": False}
            if item.get("name") is not None:
                if not isinstance(item["name"], str):
                    raise SourceError("Nome público inesperado no resultado de busca.")
                candidate["display_name"] = item["name"]
            results.append(candidate)
        return results


class GitHubNameProvider(NameProvider):
    name = "GitHub — nome"

    def url(self, query: Query) -> str:
        return "https://api.github.com/search/users?" + urlencode({"q": f'"{query.value}" in:fullname type:user', "per_page": self.limit, "page": 1})

    def parse(self, payload) -> dict:
        if (not isinstance(payload, dict) or not isinstance(payload.get("items"), list)
                or type(payload.get("total_count")) is not int or payload["total_count"] < len(payload["items"])
                or type(payload.get("incomplete_results")) is not bool):
            raise SourceError("Formato inesperado na busca do GitHub.")
        return {"candidates": self.candidates(payload["items"], "login", "https://github.com/"),
                "total_reported": payload["total_count"], "incomplete_results": payload["incomplete_results"],
                "more_results_possible": payload["total_count"] > len(payload["items"])}


class GitLabNameProvider(NameProvider):
    name = "GitLab — nome"

    def url(self, query: Query) -> str:
        return "https://gitlab.com/api/v4/users?" + urlencode({"search": query.value, "per_page": self.limit, "page": 1})

    def parse(self, payload) -> dict:
        if not isinstance(payload, list):
            raise SourceError("Formato inesperado na busca do GitLab.")
        return {"candidates": self.candidates(payload, "username", "https://gitlab.com/"),
                "more_results_possible": len(payload) == self.limit}


NAME_PROVIDERS = {"github": GitHubNameProvider, "gitlab": GitLabNameProvider}


def name_providers(client: JsonClient, platforms: list[str] | None = None, limit: int = 10) -> list[NameProvider]:
    selected = list(NAME_PROVIDERS) if platforms is None else list(dict.fromkeys(platforms))
    return [NAME_PROVIDERS[name](client, limit) for name in selected]
