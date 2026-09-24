"""Compatibilidade de importação; implementação em core.models."""
import sys
from .core import models as _implementation

sys.modules[__name__] = _implementation
