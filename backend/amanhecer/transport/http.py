"""Transporte HTTPS compartilhado, com limites e tentativas controladas."""
import json
import time
from http.client import IncompleteRead, RemoteDisconnected, BadStatusLine, LineTooLong
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlsplit
from ..core.contracts import JsonResponse, SourceError, SourceHttpError
from .. import __version__


MAX_RESPONSE_BYTES = 5_000_000
RETRYABLE_HTTP_STATUS = frozenset({500, 502, 503, 504})
READ_ERRORS = (IncompleteRead, RemoteDisconnected, BadStatusLine, LineTooLong)
TRANSIENT_ERRORS = READ_ERRORS + (URLError, TimeoutError, OSError)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpClient:
    ALLOWED_HOSTS = {"brasilapi.com.br", "dns.google", "crt.sh", "api.github.com", "gitlab.com", "gateway.apiserpro.serpro.gov.br"}

    def __init__(self, timeout: float = 15, retries: int = 2, interval: float = 0.5):
        if not 0 < timeout <= 120 or not 0 <= retries <= 5 or not 0 <= interval < float("inf"):
            raise ValueError("Configuração HTTP inválida.")
        self.timeout, self.retries, self.interval = timeout, retries, interval
        self._last_request = 0.0
        self._opener = build_opener(NoRedirect())

    def get(self, url: str):
        return self.get_response(url).data

    def build_request(self, url: str, bearer_token: str | None) -> Request:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc not in self.ALLOWED_HOSTS:
            raise SourceError("Endpoint fora da lista de fontes permitidas.")
        headers = {"Accept": "application/json", "User-Agent": f"AmanhecerOSINT/{__version__}"}
        if bearer_token is not None:
            if (parts.netloc != "gateway.apiserpro.serpro.gov.br"
                    or not parts.path.startswith("/consulta-cpf-df/v3/cpf/")):
                raise SourceError("O token de CPF só pode ser enviado ao endpoint do Serpro.")
            if not bearer_token or any(ord(char) < 33 or ord(char) > 126 for char in bearer_token):
                raise SourceError("Token do Serpro inválido.")
            headers["Authorization"] = "Bearer " + bearer_token
        if parts.netloc == "api.github.com":
            headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"})
        return Request(url, headers=headers)

    def read_response(self, request: Request) -> JsonResponse:
        time.sleep(max(0, self.interval - (time.monotonic() - self._last_request)))
        self._last_request = time.monotonic()
        with self._opener.open(request, timeout=self.timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            status_code = response.status
        if len(body) > MAX_RESPONSE_BYTES:
            raise SourceError("Resposta excede o limite de 5 MB.")
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise SourceError("A fonte retornou JSON inválido.") from exc
        return JsonResponse(status_code, payload)

    def retry_delay(self, error: HTTPError, attempt: int) -> float:
        if error.code == 429:
            raise SourceHttpError(429, "Limite de consultas da fonte atingido; tente novamente mais tarde.") from error
        if error.code not in RETRYABLE_HTTP_STATUS or attempt == self.retries:
            raise SourceHttpError(error.code) from error
        retry_after = error.headers.get("Retry-After", "") if error.headers else ""
        # Evita converter inteiros arbitrariamente grandes recebidos da fonte.
        if retry_after.isascii() and retry_after.isdigit():
            if len(retry_after) > 2 or int(retry_after) > 30:
                raise SourceHttpError(error.code, "A fonte pediu um intervalo maior; tente novamente mais tarde.") from error
            return int(retry_after)
        return 2 ** attempt

    def get_response(self, url: str, *, bearer_token: str | None = None) -> JsonResponse:
        request = self.build_request(url, bearer_token)
        for attempt in range(self.retries + 1):
            try:
                return self.read_response(request)
            except HTTPError as exc:
                try:
                    delay = self.retry_delay(exc, attempt)
                finally:
                    exc.close()
            except TRANSIENT_ERRORS as exc:
                if attempt == self.retries:
                    raise SourceError("Falha de conexão, leitura incompleta ou tempo limite na fonte.") from exc
                delay = 2 ** attempt
            time.sleep(delay)
        raise SourceError("Não foi possível concluir a requisição.")
