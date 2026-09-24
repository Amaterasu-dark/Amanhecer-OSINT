"""Composição de dependências e interface de linha de comando."""
import argparse
import os
import sys
from pathlib import Path
from .application import InvestigationService
from . import __version__
from .cpf import CpfValidationProvider, SerproCpfProvider, birth_date
from .domain import Query, QueryKind
from .http import HttpClient
from .providers import default_providers
from .reports import render_html, render_json, render_text
from .usernames import USERNAME_PROVIDERS
from .names import name_providers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Amanhecer OSINT — arroba, nome completo e CPF")
    parser.add_argument("--version", action="version", version=f"Amanhecer OSINT {__version__}")
    parser.add_argument("tipo", choices=[QueryKind.USERNAME.value, QueryKind.NAME.value, QueryKind.CPF.value])
    parser.add_argument("valor", help="Arroba, nome completo entre aspas ou CPF (no PowerShell, use aspas: '@apelido')")
    parser.add_argument("--plataforma", action="append", choices=list(USERNAME_PROVIDERS), help="Fonte de arroba/nome; pode ser repetida. Padrão: todas as disponíveis")
    parser.add_argument("--limite", type=int, help="Busca por nome: 1 a 50 candidatos por fonte; padrão 10")
    parser.add_argument("--nascimento", help="CPF no Serpro: data de nascimento no formato AAAA-MM-DD")
    parser.add_argument("--somente-validar", action="store_true", help="CPF: conferir apenas formato e dígitos, sem consultar cadastro ou usar rede")
    parser.add_argument("--formato", choices=("texto", "json", "html"), default="texto")
    parser.add_argument("--saida", type=Path, help="Arquivo novo para o relatório")
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args(argv)
    try:
        query = Query(QueryKind(args.tipo), args.valor)
        if query.kind != QueryKind.CPF and (args.nascimento or args.somente_validar):
            raise ValueError("--nascimento e --somente-validar só se aplicam a CPF.")
        if query.kind != QueryKind.NAME and args.limite is not None:
            raise ValueError("--limite só se aplica à busca por nome.")
        if query.kind == QueryKind.CPF and args.plataforma:
            raise ValueError("A fonte de CPF é o Serpro; --plataforma só se aplica a arroba/nome.")
        if args.limite is not None and not 1 <= args.limite <= 50:
            raise ValueError("--limite deve estar entre 1 e 50.")
        if args.saida and args.saida.exists():
            raise ValueError("O arquivo de saída já existe; escolha outro nome.")
        if query.kind == QueryKind.CPF:
            if args.somente_validar:
                if args.nascimento:
                    raise ValueError("--somente-validar não usa data de nascimento; remova --nascimento.")
                providers = [CpfValidationProvider()]
            else:
                if not args.nascimento:
                    raise ValueError("Consulta CPF exige --nascimento AAAA-MM-DD e AMANHECER_SERPRO_TOKEN. Para conferir apenas dígitos, use --somente-validar.")
                birth_date(args.nascimento)
                token = os.environ.get("AMANHECER_SERPRO_TOKEN", "")
                if not token:
                    raise ValueError("Configure AMANHECER_SERPRO_TOKEN com o token do serviço Serpro contratado. Nenhuma consulta foi realizada.")
                # Repetições de consultas de produção podem gerar cobranças adicionais.
                providers = [SerproCpfProvider(HttpClient(timeout=args.timeout, retries=0), token, args.nascimento)]
        else:
            client = HttpClient(timeout=args.timeout)
            providers = (name_providers(client, args.plataforma, args.limite or 10) if query.kind == QueryKind.NAME
                         else default_providers(client, args.plataforma))
        report = InvestigationService(providers).investigate(query)
        output = {"texto": render_text, "json": render_json, "html": render_html}[args.formato](report)
        if args.saida:
            args.saida.parent.mkdir(parents=True, exist_ok=True)
            with args.saida.open("x", encoding="utf-8") as stream:
                stream.write(output + "\n")
            print(f"Relatório salvo em {args.saida}", file=sys.stderr)
        else:
            print(output)
        return 1 if any(result.status == "error" for result in report.results) else 0
    except (ValueError, OSError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Consulta interrompida.", file=sys.stderr)
        return 130
