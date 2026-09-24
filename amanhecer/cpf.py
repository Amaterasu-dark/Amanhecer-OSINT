"""Compatibilidade com os imports anteriores de CPF."""
from .sources.serpro import SERPRO_BASE, birth_date, SerproCpfProvider
from .sources.local import CpfValidationProvider
