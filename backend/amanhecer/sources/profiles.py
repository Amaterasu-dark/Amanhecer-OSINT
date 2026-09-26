"""Fluxos comuns de perfis; URLs e payloads pertencem a cada serviço."""
from abc import ABC, abstractmethod
from urllib.parse import quote
import re
from ..core.models import Evidence, Query, QueryKind
from ..core.contracts import JsonClient, SourceError, SourceHttpError


IDENTITY_NOTE = "O mesmo arroba em plataformas diferentes não confirma que os perfis pertencem à mesma pessoa."


class UsernameProvider(ABC):
    name: str
    profile_base: str
    not_found_on_404 = False

    def __init__(self, client: JsonClient):
        self.client = client

    def supports(self, query: Query) -> bool:
        return query.kind == QueryKind.USERNAME

    @abstractmethod
    def url(self, query: Query) -> str: ...

    @abstractmethod
    def parse(self, payload, query: Query) -> dict | None: ...

    def collect(self, query: Query) -> Evidence:
        url = self.url(query)
        data = {"username": query.value, "match": "inconclusive", "note": IDENTITY_NOTE}
        try:
            profile = self.parse(self.client.get(url), query)
        except SourceHttpError as exc:
            if exc.status_code == 404 and self.not_found_on_404:
                profile = None
            else:
                return Evidence(self.name, url, "error", data=data, error=str(exc))
        except SourceError as exc:
            return Evidence(self.name, url, "error", data=data, error=str(exc))
        if profile is None:
            data.update(match="not_found", detail="Nenhum perfil público retornado para este arroba nesta fonte.")
        else:
            data.update(match="found", profile=profile)
        return Evidence(self.name, url, "ok", data=data)

    def profile(self, payload: dict, username: str, fields: dict[str, str]) -> dict:
        result = {"username": username, "profile_url": self.profile_base + quote(username, safe="")}
        for target, source in fields.items():
            value = payload.get(source)
            if value is not None:
                if not isinstance(value, (str, int)) or isinstance(value, bool):
                    raise SourceError("Formato inesperado nos dados do perfil público.")
                result[target] = value
        return result


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


