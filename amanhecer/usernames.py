"""Compatibilidade com os imports anteriores de usernames."""
from .sources.profiles import UsernameProvider, IDENTITY_NOTE
from .sources.github import GitHubUsernameProvider
from .sources.gitlab import GitLabUsernameProvider
from .sources.registry import USERNAME_PROVIDERS, username_providers
