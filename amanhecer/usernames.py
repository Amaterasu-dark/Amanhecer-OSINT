"""Consulta exata de arrobas em APIs de perfis públicos."""
from abc import ABC, abstractmethod
from urllib.parse import quote, urlencode

from .domain import Evidence, Query, QueryKind
from .ports import JsonClient, SourceError, SourceHttpError


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


USERNAME_PROVIDERS = {"github": GitHubUsernameProvider, "gitlab": GitLabUsernameProvider}


def username_providers(client: JsonClient, platforms: list[str] | None = None) -> list[UsernameProvider]:
    selected = list(USERNAME_PROVIDERS) if platforms is None else list(dict.fromkeys(platforms))
    return [USERNAME_PROVIDERS[name](client) for name in selected]
