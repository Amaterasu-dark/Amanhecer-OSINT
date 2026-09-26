"""Compatibilidade de importação; implementação em commands.cli."""
import sys
from .commands import cli as _implementation

sys.modules[__name__] = _implementation
