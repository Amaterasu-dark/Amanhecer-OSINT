"""Compatibilidade com os imports anteriores de names."""
from .sources.profiles import NameProvider, NAME_NOTE
from .sources.github import GitHubNameProvider
from .sources.gitlab import GitLabNameProvider
from .sources.registry import NAME_PROVIDERS, name_providers
