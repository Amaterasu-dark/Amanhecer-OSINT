"""Compatibilidade de importação; implementação em transport.http."""
import sys
from .transport import http as _implementation

sys.modules[__name__] = _implementation
