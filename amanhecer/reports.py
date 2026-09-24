"""Serialização JSON e HTML com escape de conteúdo externo."""
import json
import unicodedata
from html import escape
from .domain import QueryKind, Report, display_query


def terminal_text(value) -> str:
    """Impede que conteúdo externo controle o terminal ou simule novas linhas."""
    return "".join(" " if unicodedata.category(char).startswith("C") or char in "\u2028\u2029" else char for char in str(value))


def render_text(report: Report) -> str:
    target = display_query(report.query)
    if report.query.kind == QueryKind.USERNAME:
        target = "@" + target
    lines = [f"Amanhecer OSINT | {report.query.kind.value}: {terminal_text(target)}", f"Coleta: {report.created_at}", ""]
    labels = {"found": "ENCONTRADO", "not_found": "NÃO ENCONTRADO", "inconclusive": "INCONCLUSIVO", "candidates": "CANDIDATOS", "validated": "DÍGITOS VÁLIDOS"}
    for result in report.results:
        data = result.data or {}
        match = data.get("match", "inconclusive")
        lines.append(f"[{labels.get(match, 'INCONCLUSIVO')}] {terminal_text(result.provider)}")
        profile = data.get("profile", {})
        for label, key in [("Perfil", "profile_url"), ("Nome público", "display_name"), ("Bio", "bio"), ("Tipo de conta", "account_type")]:
            if profile.get(key):
                lines.append(f"  {label}: {terminal_text(profile[key])}")
        for candidate in data.get("candidates", []):
            name = candidate.get("display_name", candidate["username"])
            lines.append(f"  - {terminal_text(name)} (@{terminal_text(candidate['username'])}): {terminal_text(candidate['profile_url'])}")
        if data.get("more_results_possible"):
            lines.append("  Pode haver mais resultados na fonte além desta página.")
        record = data.get("record", {})
        for label, key in [("Nome cadastral", "name"), ("Situação cadastral", "registration_status")]:
            if record.get(key):
                lines.append(f"  {label}: {terminal_text(record[key])}")
        if data.get("detail"):
            lines.append(f"  {terminal_text(data['detail'])}")
        if result.error:
            lines.append(f"  Motivo: {terminal_text(result.error)}")
        lines.append(f"  Fonte: {terminal_text(result.source_url)}")
        lines.append("")
    if report.query.kind == QueryKind.USERNAME:
        lines.append("O mesmo arroba em plataformas diferentes não confirma que os perfis pertencem à mesma pessoa.")
    elif report.query.kind == QueryKind.NAME:
        lines.append("Resultados por nome podem incluir homônimos ou correspondências aproximadas; a identidade não foi confirmada.")
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
