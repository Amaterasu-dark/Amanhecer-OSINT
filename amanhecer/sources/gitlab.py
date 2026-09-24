"""Consultas de perfil e nome no GitLab."""
from urllib.parse import quote, urlencode
from ..core.models import Query
from ..core.contracts import SourceError
from .profiles import UsernameProvider, NameProvider


class GitLabUsernameProvider(UsernameProvider):
    name = "GitLab"
    profile_base = "https://gitlab.com/"

    def url(self, query: Query) -> str:
        return "https://gitlab.com/api/v4/users?" + urlencode({"username": query.value})

    def parse(self, payload, query: Query) -> dict | None:
        if not isinstance(payload, list):
            raise SourceError("Formato inesperado na resposta do GitLab.")
        if not payload:
            return None
        if len(payload) != 1 or not isinstance(payload[0], dict) or not isinstance(payload[0].get("username"), str):
            raise SourceError("Resposta inesperada na consulta exata ao GitLab.")
        item = payload[0]
        username = item["username"]
        if username.casefold() != query.value.casefold():
            raise SourceError("O GitLab retornou outro arroba; a correspondência não foi confirmada.")
        return self.profile(item, username, {"platform_id": "id", "display_name": "name", "state": "state"})


class GitLabNameProvider(NameProvider):
    name = "GitLab — nome"

    def url(self, query: Query) -> str:
        return "https://gitlab.com/api/v4/users?" + urlencode({"search": query.value, "per_page": self.limit, "page": 1})

    def parse(self, payload) -> dict:
        if not isinstance(payload, list):
            raise SourceError("Formato inesperado na busca do GitLab.")
        return {"candidates": self.candidates(payload, "username", "https://gitlab.com/"),
                "more_results_possible": len(payload) == self.limit}


