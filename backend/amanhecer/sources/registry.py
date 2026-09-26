"""Capacidades das plataformas por tipo de consulta."""
from dataclasses import dataclass
from ..core.models import QueryKind
from ..core.contracts import JsonClient
from .profiles import NameProvider, UsernameProvider
from .github import GitHubNameProvider, GitHubUsernameProvider
from .gitlab import GitLabNameProvider, GitLabUsernameProvider


@dataclass(frozen=True)
class Platform:
    username: type[UsernameProvider] | None = None
    name: type[NameProvider] | None = None


PLATFORMS = {
    "github": Platform(GitHubUsernameProvider, GitHubNameProvider),
    "gitlab": Platform(GitLabUsernameProvider, GitLabNameProvider),
}


def available_platforms(kind: QueryKind) -> tuple[str, ...]:
    match kind:
        case QueryKind.USERNAME:
            return tuple(key for key, platform in PLATFORMS.items() if platform.username)
        case QueryKind.NAME:
            return tuple(key for key, platform in PLATFORMS.items() if platform.name)
        case _:
            return ()


def select_platforms(kind: QueryKind, requested: list[str] | None) -> list[str]:
    available = available_platforms(kind)
    selected = list(available) if requested is None else list(dict.fromkeys(requested))
    for name in selected:
        if name not in available:
            raise ValueError(f"Plataforma {name!r} indisponível para {kind.value}.")
    return selected


def username_providers(client: JsonClient, platforms: list[str] | None = None) -> list[UsernameProvider]:
    providers = []
    for name in select_platforms(QueryKind.USERNAME, platforms):
        provider = PLATFORMS[name].username
        if provider is not None:
            providers.append(provider(client))
    return providers


def name_providers(client: JsonClient, platforms: list[str] | None = None, limit: int = 10) -> list[NameProvider]:
    providers = []
    for name in select_platforms(QueryKind.NAME, platforms):
        provider = PLATFORMS[name].name
        if provider is not None:
            providers.append(provider(client, limit))
    return providers


# Visões de compatibilidade; o registro acima é a única fonte da composição.
USERNAME_PROVIDERS = {key: value.username for key, value in PLATFORMS.items() if value.username}
NAME_PROVIDERS = {key: value.name for key, value in PLATFORMS.items() if value.name}
