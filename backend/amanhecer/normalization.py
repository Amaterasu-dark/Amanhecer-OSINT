"""Compatibilidade de importação; implementação em core.normalization."""
import sys
from .core import normalization as _implementation

sys.modules[__name__] = _implementation
