"""Serialização JSON e HTML com escape de conteúdo externo."""
import json
import unicodedata
from html import escape
from ..core.models import Evidence, QueryKind, Report, display_query


def terminal_text(value) -> str:
    """Impede que conteúdo externo controle o terminal ou simule novas linhas."""
    return "".join(" " if unicodedata.category(char).startswith("C") or char in "\u2028\u2029" else char for char in str(value))


MATCH_LABELS = {
    "found": "ENCONTRADO", "not_found": "NÃO ENCONTRADO",
    "inconclusive": "INCONCLUSIVO", "candidates": "CANDIDATOS",
    "validated": "DÍGITOS VÁLIDOS", "format_valid": "FORMATO COMPATÍVEL",
    "region": "REGIÃO DO DDD",
}
PROFILE_FIELDS = (
    ("Perfil", "profile_url"), ("Nome público", "display_name"),
    ("Bio", "bio"), ("Tipo de conta", "account_type"),
)
RECORD_FIELDS = (
    ("Nome cadastral", "name"), ("Situação cadastral", "registration_status"),
    ("CNPJ", "cnpj"), ("Nome fantasia", "trade_name"), ("Início de atividade", "started_at"),
    ("Atividade principal", "activity"), ("Município", "city"), ("UF", "state"),
    ("Logradouro", "street"), ("Número", "number"), ("Complemento", "complement"),
    ("Bairro", "district"), ("CEP", "postal_code"),
)
QUERY_NOTES = {
    QueryKind.USERNAME: "O mesmo arroba em plataformas diferentes não confirma que os perfis pertencem à mesma pessoa.",
    QueryKind.NAME: "Resultados por nome podem incluir homônimos ou correspondências aproximadas; a identidade não foi confirmada.",
}


def render_fields(data: dict, fields: tuple[tuple[str, str], ...]) -> list[str]:
    return [f"  {label}: {terminal_text(data[key])}" for label, key in fields if data.get(key)]


def render_candidates(data: dict) -> list[str]:
    lines = []
    for candidate in data.get("candidates", []):
        name = candidate.get("display_name") or candidate["username"]
        lines.append(f"  - {terminal_text(name)} (@{terminal_text(candidate['username'])}): {terminal_text(candidate['profile_url'])}")
    if data.get("more_results_possible"):
        lines.append("  Pode haver mais resultados na fonte além desta página.")
    return lines


def render_phone(data: dict) -> list[str]:
    lines = []
    phone = data.get("phone", {})
    if phone:
        lines.append(f"  DDD: {terminal_text(phone['ddd'])} | Tipo: {terminal_text(phone['type'])}")
    region = data.get("region", {})
    if region:
        lines.append(f"  DDD: {terminal_text(region['ddd'])} | UF: {terminal_text(region['state'])}")
        lines.append(f"  Municípios do DDD: {terminal_text(', '.join(region['cities']))}")
    return lines


def render_evidence(result: Evidence) -> list[str]:
    result = result.validated()
    data = result.data or {}
    label = MATCH_LABELS.get(data.get("match"), "INCONCLUSIVO")
    lines = [f"[{label}] {terminal_text(result.provider)}"]
    lines.extend(render_fields(data.get("profile", {}), PROFILE_FIELDS))
    lines.extend(render_candidates(data))
    lines.extend(render_fields(data.get("record", {}), RECORD_FIELDS))
    lines.extend(render_phone(data))
    if data.get("detail"):
        lines.append(f"  {terminal_text(data['detail'])}")
    if result.error:
        lines.append(f"  Motivo: {terminal_text(result.error)}")
    lines.extend([f"  Fonte: {terminal_text(result.source_url)}", ""])
    return lines


def render_text(report: Report) -> str:
    target = display_query(report.query)
    if report.query.kind == QueryKind.USERNAME:
        target = "@" + target
    lines = [f"Amanhecer OSINT | {report.query.kind.value}: {terminal_text(target)}", f"Coleta: {report.created_at}", ""]
    for result in report.unique_results():
        lines.extend(render_evidence(result))
    note = QUERY_NOTES.get(report.query.kind)
    if note:
        lines.append(note)
    return "\n".join(lines)


def render_json(report: Report) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render_html(report: Report) -> str:
    content = escape(render_json(report))
    return ('<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            '<title>Amanhecer OSINT</title><style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:20px;background:#101820;color:#e7eff5}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
            f'<h1>Amanhecer OSINT</h1><pre>{content}</pre></html>')
