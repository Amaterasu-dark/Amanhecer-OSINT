"""Compatibilidade de importação; implementação em core.service."""
import sys
from .core import service as _implementation

sys.modules[__name__] = _implementation
