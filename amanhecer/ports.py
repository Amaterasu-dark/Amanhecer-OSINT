"""Compatibilidade de importação; implementação em core.contracts."""
import sys
from .core import contracts as _implementation

sys.modules[__name__] = _implementation
