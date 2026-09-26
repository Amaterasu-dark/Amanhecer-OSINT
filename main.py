"""Atalho para executar o backend a partir da raiz do projeto."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from amanhecer.commands.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
