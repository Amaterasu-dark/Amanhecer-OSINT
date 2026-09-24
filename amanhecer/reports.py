"""Compatibilidade de importação; implementação em reporting.renderers."""
import sys
from .reporting import renderers as _implementation

sys.modules[__name__] = _implementation
