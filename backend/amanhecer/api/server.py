"""Servidor de desenvolvimento restrito à interface local."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import __version__
from .controller import ConfigurationError, ConsultationController, ROUTES


MAX_BODY = 16_384


class ApiHandler(BaseHTTPRequestHandler):
    controller = ConsultationController()

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        # Não registrar identificadores, corpo, credenciais ou URLs de entrada.
        pass

    def reply(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if status == 405:
            self.send_header("Allow", "GET" if self.path == "/health" else "POST")
        self.end_headers()
        self.wfile.write(data)

    def send_error(self, code, message=None, explain=None):
        self.reply(code, {"error": {"message": "Requisição HTTP não suportada."}})

    def do_GET(self):
        if self.path == "/health":
            self.reply(200, {"status": "ok", "version": __version__})
        else:
            self.reply(405 if self.path in ROUTES else 404,
                       {"error": {"message": "Método não permitido ou rota inexistente."}})

    def do_POST(self):
        if self.path not in ROUTES:
            self.reply(405 if self.path == "/health" else 404,
                       {"error": {"message": "Método não permitido ou rota inexistente."}})
            return
        if self.headers.get_content_type() != "application/json":
            self.reply(415, {"error": {"message": "Use Content-Type: application/json."}})
            return
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Transfer-Encoding não suportado.")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1:
                raise ValueError("Informe um Content-Length.")
            length = int(lengths[0])
            if length <= 0:
                raise ValueError("Informe um corpo JSON.")
            if length > MAX_BODY:
                self.reply(413, {"error": {"message": "Corpo excede 16 KB."}})
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Corpo incompleto.")
            try:
                body = json.loads(raw)
            except (ValueError, UnicodeError, RecursionError):
                raise ValueError("JSON inválido.") from None
            status, result = self.controller.consult(ROUTES[self.path], body)
        except ValueError as exc:
            status, result = 400, {"error": {"message": str(exc)}}
        except ConfigurationError as exc:
            status, result = 503, {"error": {"message": str(exc)}}
        except TimeoutError:
            status, result = 408, {"error": {"message": "Tempo de leitura esgotado."}}
        except Exception:
            status, result = 500, {"error": {"message": "Falha interna ao processar a consulta."}}
        self.reply(status, result)

    def do_PUT(self):
        self.reply(405 if self.path in ROUTES or self.path == "/health" else 404,
                   {"error": {"message": "Método não permitido ou rota inexistente."}})

    do_DELETE = do_PUT
    do_PATCH = do_PUT
    do_OPTIONS = do_PUT


def create_server(port=8000):
    return ThreadingHTTPServer(("127.0.0.1", port), ApiHandler)


def main():
    parser = argparse.ArgumentParser(description="API local do Amanhecer")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    with create_server(args.port) as server:
        print(f"Amanhecer disponível em http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
