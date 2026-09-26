"""Entrada direta do backend, sem depender do diretório atual."""
from amanhecer.commands.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
