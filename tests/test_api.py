import json
import os
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import patch

from amanhecer.api.server import create_server
from amanhecer.core.contracts import JsonResponse


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, body=None, method="POST", content_type="application/json"):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body, {"Content-Type": content_type})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_health_and_routing(self):
        self.assertEqual(self.request("/health", method="GET")[0], 200)
        self.assertEqual(self.request("/missing", method="GET")[0], 404)
        self.assertEqual(self.request("/api/v1/cpf", method="GET")[0], 405)
        self.assertEqual(self.request("/health", method="POST")[0], 405)

    @patch("amanhecer.transport.http.HttpClient.get_response", side_effect=AssertionError("No network"))
    def test_local_routes_and_cpf_masking(self, network):
        for route, value in [("cpf", "40442820135"), ("cnpj", "00000000000191"),
                             ("telefone", "11912345678")]:
            status, result = self.request("/api/v1/" + route, json.dumps({"valor": value, "somente_validar": True}))
            self.assertEqual(status, 200, result)
            if route == "cpf":
                self.assertNotIn(value, json.dumps(result))
        network.assert_not_called()

    def test_bad_payloads(self):
        for body in ["{", "[]", "null", '{}', '{"valor": 123}',
                     '{"valor":"octocat","plataformas":null}',
                     '{"valor":"octocat","somente_validar":true}']:
            self.assertEqual(self.request("/api/v1/arroba", body)[0], 400, body)
        self.assertEqual(self.request("/api/v1/nome", '{"valor":"Maria Silva","limite":true}')[0], 400)
        self.assertEqual(self.request("/api/v1/cpf", "{}", content_type="text/plain")[0], 415)
        self.assertEqual(self.request("/api/v1/cpf", " " * 16385)[0], 413)

    def test_missing_serpro_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            status, _ = self.request("/api/v1/cpf", json.dumps({"valor":"40442820135", "nascimento":"1970-11-14"}))
        self.assertEqual(status, 503)

    @patch("amanhecer.transport.http.HttpClient.get_response")
    def test_upstream_success_and_failure(self, network):
        from amanhecer.core.contracts import SourceError
        network.return_value = JsonResponse(200, {"login":"octocat", "html_url":"https://github.com/octocat"})
        body = json.dumps({"valor":"octocat", "plataformas":["github"]})
        self.assertEqual(self.request("/api/v1/arroba", body)[0], 200)
        network.side_effect = SourceError("unavailable")
        status, result = self.request("/api/v1/arroba", body)
        self.assertEqual(status, 502)
        self.assertEqual(result["results"][0]["status"], "error")
