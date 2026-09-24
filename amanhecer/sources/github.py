"""Consultas de perfil e nome no GitHub."""
from urllib.parse import quote, urlencode
from ..core.models import Query
from ..core.contracts import SourceError
from .profiles import UsernameProvider, NameProvider


class GitHubUsernameProvider(UsernameProvider):
    name = "GitHub"
    profile_base = "https://github.com/"
    not_found_on_404 = True

    def url(self, query: Query) -> str:
        return "https://api.github.com/users/" + quote(query.value, safe="")

    def parse(self, payload, query: Query) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("login"), str):
            raise SourceError("Formato inesperado na resposta do GitHub.")
        username = payload["login"]
        if username.casefold() != query.value.casefold():
            raise SourceError("O GitHub retornou outro arroba; a correspondência não foi confirmada.")
        return self.profile(payload, username, {
            "platform_id": "id", "display_name": "name", "bio": "bio",
            "account_type": "type", "public_repos": "public_repos",
            "followers": "followers", "created_at": "created_at",
        })


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


