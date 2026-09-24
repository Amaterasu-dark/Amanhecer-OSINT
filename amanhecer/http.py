"""HTTP com TLS, limites e tentativas controladas."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlsplit
from .ports import JsonResponse, SourceError, SourceHttpError
from . import __version__


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpClient:
    ALLOWED_HOSTS = {"brasilapi.com.br", "dns.google", "crt.sh", "api.github.com", "gitlab.com", "gateway.apiserpro.serpro.gov.br"}

    def __init__(self, timeout: float = 15, retries: int = 2, interval: float = 0.5):
        if not 0 < timeout <= 120 or not 0 <= retries <= 5 or interval < 0:
            raise ValueError("Configuração HTTP inválida.")
        self.timeout, self.retries, self.interval = timeout, retries, interval
        self._last_request = 0.0
        self._opener = build_opener(NoRedirect())

    def get(self, url: str):
        return self.get_response(url).data

    def get_response(self, url: str, *, bearer_token: str | None = None) -> JsonResponse:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc not in self.ALLOWED_HOSTS:
            raise SourceError("Endpoint fora da lista de fontes permitidas.")
        if bearer_token is not None:
            if (parts.netloc != "gateway.apiserpro.serpro.gov.br"
                    or not parts.path.startswith("/consulta-cpf-df/v3/cpf/")):
                raise SourceError("O token de CPF só pode ser enviado ao endpoint do Serpro.")
            if not bearer_token or any(ord(char) < 33 or ord(char) > 126 for char in bearer_token):
                raise SourceError("Token do Serpro inválido.")
        for attempt in range(self.retries + 1):
            time.sleep(max(0, self.interval - (time.monotonic() - self._last_request)))
            self._last_request = time.monotonic()
            try:
                headers = {"Accept": "application/json", "User-Agent": f"AmanhecerOSINT/{__version__}"}
                if bearer_token is not None:
                    headers["Authorization"] = "Bearer " + bearer_token
                if parts.netloc == "api.github.com":
                    headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"})
                request = Request(url, headers=headers)
                with self._opener.open(request, timeout=self.timeout) as response:
                    body = response.read(5_000_001)
                    status_code = response.status
                if len(body) > 5_000_000:
                    raise SourceError("Resposta excede o limite de 5 MB.")
                return JsonResponse(status_code, json.loads(body))
            except HTTPError as exc:
                exc.close()
                if exc.code == 429:
                    raise SourceHttpError(429, "Limite de consultas da fonte atingido; tente novamente mais tarde.") from exc
                if exc.code not in (500, 502, 503, 504) or attempt == self.retries:
                    raise SourceHttpError(exc.code) from exc
                retry_after = exc.headers.get("Retry-After", "")
                delay = int(retry_after) if retry_after.isdigit() else 2 ** attempt
                if delay > 30:
                    raise SourceHttpError(exc.code, f"Limite da fonte: tente novamente em {delay}s.") from exc
                time.sleep(delay)
            except (URLError, TimeoutError, OSError) as exc:
                if attempt == self.retries:
                    raise SourceError("Falha de conexão ou tempo limite na fonte.") from exc
                time.sleep(2 ** attempt)
            except (ValueError, UnicodeError) as exc:
                raise SourceError("A fonte retornou JSON inválido.") from exc
