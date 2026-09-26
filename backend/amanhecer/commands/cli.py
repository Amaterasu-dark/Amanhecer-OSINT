"""Composição de dependências e interface de linha de comando."""
import argparse
import os
import sys
from pathlib import Path
from ..core.service import InvestigationService
from .. import __version__
from ..sources.serpro import SerproCpfProvider, birth_date
from ..sources.brasilapi import CnpjProvider, PhoneRegionProvider
from ..sources.local import CpfValidationProvider, CnpjValidationProvider, PhoneValidationProvider
from ..core.models import Query, QueryKind, Report
from ..core.contracts import Provider
from ..transport.http import HttpClient
from ..reporting.renderers import render_html, render_json, render_text
from ..sources.registry import name_providers, username_providers, select_platforms


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Amanhecer OSINT — arroba, nome, CPF, CNPJ e telefone")
    parser.add_argument("--version", action="version", version=f"Amanhecer OSINT {__version__}")
    parser.add_argument("tipo", choices=[kind.value for kind in (QueryKind.USERNAME, QueryKind.NAME, QueryKind.CPF, QueryKind.CNPJ, QueryKind.PHONE)])
    parser.add_argument("valor", help="Arroba, nome completo, CPF, CNPJ ou telefone com DDD; use aspas para espaços e @")
    parser.add_argument("--plataforma", action="append", help="Fonte compatível com o tipo de consulta; pode ser repetida. Padrão: todas as disponíveis")
    parser.add_argument("--limite", type=int, help="Busca por nome: 1 a 50 candidatos por fonte; padrão 10")
    parser.add_argument("--nascimento", help="CPF no Serpro: data de nascimento no formato AAAA-MM-DD")
    parser.add_argument("--somente-validar", action="store_true", help="CPF/CNPJ: conferir formato e dígitos; telefone: conferir formato. Sem rede")
    parser.add_argument("--formato", choices=("texto", "json", "html"), default="texto")
    parser.add_argument("--saida", type=Path, help="Arquivo novo para o relatório")
    parser.add_argument("--timeout", type=float, default=15)
    return parser


def validate_options(args: argparse.Namespace, kind: QueryKind) -> None:
    """Valida combinações antes de criar clientes ou consultar fontes."""
    restrictions = (
        (args.nascimento, {QueryKind.CPF}, "--nascimento só se aplica a CPF."),
        (args.somente_validar, {QueryKind.CPF, QueryKind.CNPJ, QueryKind.PHONE},
         "--somente-validar só se aplica a CPF, CNPJ ou telefone."),
        (args.limite is not None, {QueryKind.NAME}, "--limite só se aplica à busca por nome."),
        (args.plataforma, {QueryKind.USERNAME, QueryKind.NAME}, "--plataforma só se aplica a arroba/nome."),
    )
    for enabled, allowed, message in restrictions:
        if enabled and kind not in allowed:
            raise ValueError(message)
    if args.plataforma:
        select_platforms(kind, args.plataforma)
    if args.limite is not None and not 1 <= args.limite <= 50:
        raise ValueError("--limite deve estar entre 1 e 50.")
    if args.saida and args.saida.exists():
        raise ValueError("O arquivo de saída já existe; escolha outro nome.")


def build_cpf_providers(args: argparse.Namespace) -> list[Provider]:
    if args.somente_validar:
        if args.nascimento:
            raise ValueError("--somente-validar não usa data de nascimento; remova --nascimento.")
        return [CpfValidationProvider()]
    if not args.nascimento:
        raise ValueError("Consulta CPF exige --nascimento AAAA-MM-DD e AMANHECER_SERPRO_TOKEN. Para conferir apenas dígitos, use --somente-validar.")
    birth_date(args.nascimento)
    token = os.environ.get("AMANHECER_SERPRO_TOKEN", "")
    if not token:
        raise ValueError("Configure AMANHECER_SERPRO_TOKEN com o token do serviço Serpro contratado. Nenhuma consulta foi realizada.")
    # Repetições de consultas de produção podem gerar cobranças adicionais.
    client = HttpClient(timeout=args.timeout, retries=0)
    return [SerproCpfProvider(client, token, args.nascimento)]


def build_cnpj_providers(args: argparse.Namespace) -> list[Provider]:
    if args.somente_validar:
        return [CnpjValidationProvider()]
    return [CnpjProvider(HttpClient(timeout=args.timeout))]


def build_phone_providers(args: argparse.Namespace) -> list[Provider]:
    providers: list[Provider] = [PhoneValidationProvider()]
    if not args.somente_validar:
        providers.append(PhoneRegionProvider(HttpClient(timeout=args.timeout)))
    return providers


def build_providers(kind: QueryKind, args: argparse.Namespace) -> list[Provider]:
    """Ponto de composição: cria transportes e os injeta nas fontes."""
    match kind:
        case QueryKind.CPF:
            return build_cpf_providers(args)
        case QueryKind.CNPJ:
            return build_cnpj_providers(args)
        case QueryKind.PHONE:
            return build_phone_providers(args)
        case QueryKind.NAME:
            return name_providers(HttpClient(timeout=args.timeout), args.plataforma, args.limite or 10)
        case QueryKind.USERNAME:
            return username_providers(HttpClient(timeout=args.timeout), args.plataforma)
        case _:
            raise ValueError("Tipo de consulta não disponível na CLI.")


def write_report(report: Report, output_format: str, destination: Path | None) -> None:
    renderers = {"texto": render_text, "json": render_json, "html": render_html}
    output = renderers[output_format](report)
    if destination is None:
        print(output)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(output + "\n")
    print(f"Relatório salvo em {destination}", file=sys.stderr)


def execute(args: argparse.Namespace, *, service: InvestigationService | None = None) -> int:
    """Executa a CLI; um chamador local pode fornecer um serviço já composto."""
    query = Query(QueryKind(args.tipo), args.valor)
    validate_options(args, query.kind)
    if service is None:
        service = InvestigationService(build_providers(query.kind, args))
    report = service.investigate(query)
    write_report(report, args.formato, args.saida)
    return 1 if any(result.status == "error" for result in report.results) else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return execute(args)
    except (ValueError, OSError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Consulta interrompida.", file=sys.stderr)
        return 130
