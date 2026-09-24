"""Compatibilidade do protótipo; a CLI usa o registro atual de fontes."""
from .sources.legacy import RemoteProvider, BrasilApiProvider, DnsProvider, CertificateProvider, legacy_providers
from .sources.registry import username_providers as default_providers
