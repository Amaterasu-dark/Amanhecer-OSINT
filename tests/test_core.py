import io
import json
import unittest
from uuid import uuid4
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from amanhecer.application import InvestigationService
from amanhecer.cli import main
from amanhecer.domain import Evidence, Query, QueryKind, Report
from amanhecer.http import HttpClient
from amanhecer.ports import SourceError
from amanhecer.providers import BrasilApiProvider, CertificateProvider, DnsProvider, legacy_providers
from amanhecer.reports import render_html, render_json


class DomainTests(unittest.TestCase):
    def test_cnpj_numeric_and_alphanumeric(self):
        for value, expected in [("00.000.000/0001-91", "00000000000191"), ("12.ABC.345/01DE-35", "12ABC34501DE35")]:
            self.assertEqual(Query(QueryKind.CNPJ, value).value, expected)

    def test_invalid_inputs(self):
        for kind, value in [(QueryKind.CNPJ, "00000000000000"), (QueryKind.CNPJ, "00000000000190"), (QueryKind.CEP, "abc01001000"), (QueryKind.DDD, "1"), (QueryKind.BANK, "abc"), (QueryKind.DOMAIN, "https://example.com"), (QueryKind.DOMAIN, "a..com"), (QueryKind.DOMAIN, "127.0.0.1"), (QueryKind.DOMAIN, "-a.com")]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                Query(kind, value)

    def test_normalization(self):
        self.assertEqual(Query(QueryKind.CEP, "01001-000").value, "01001000")
        self.assertEqual(Query(QueryKind.DOMAIN, "EXAMPLE.COM.").value, "example.com")
        self.assertEqual(Query(QueryKind.DOMAIN, "ação.com.br").value, "xn--ao-siap.com.br")


class ProviderTests(unittest.TestCase):
    def test_cep_endpoint_and_provenance(self):
        client = Mock()
        client.get.return_value = {"cep": "01001000"}
        result = BrasilApiProvider(client).collect(Query(QueryKind.CEP, "01001-000"))
        client.get.assert_called_once_with("https://brasilapi.com.br/api/cep/v2/01001000")
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.collected_at.endswith("+00:00"))

    def test_provider_selection(self):
        providers = legacy_providers(Mock())
        for value, count in [("example.com", 7), ("example.com.br", 8)]:
            self.assertEqual(sum(p.supports(Query(QueryKind.DOMAIN, value)) for p in providers), count)

    def test_partial_failure_keeps_other_results(self):
        client = Mock()
        client.get.side_effect = [SourceError("indisponível"), {"Status": 0, "Answer": []}]
        report = InvestigationService([DnsProvider(client, "A"), DnsProvider(client, "MX")]).investigate(Query(QueryKind.DOMAIN, "example.com"))
        self.assertEqual([r.status for r in report.results], ["error", "ok"])

    def test_dns_failure_and_nxdomain(self):
        client = Mock()
        for status, expected in [(2, "error"), (3, "ok"), (0, "ok")]:
            client.get.return_value = {"Status": status}
            result = DnsProvider(client, "A").collect(Query(QueryKind.DOMAIN, "example.com"))
            self.assertEqual(result.status, expected)
            if status == 3:
                self.assertTrue(result.data["nxdomain"])

    def test_certificate_scope_and_deduplication(self):
        client = Mock()
        client.get.return_value = [{"name_value": "*.example.com\nwww.example.com\nWWW.EXAMPLE.COM\nevil-example.com\nexample.com.evil.org"}]
        result = CertificateProvider(client).collect(Query(QueryKind.DOMAIN, "example.com"))
        self.assertEqual(result.data["domains"], ["example.com", "www.example.com"])

    def test_malformed_certificate_response(self):
        client = Mock()
        for payload in [{}, [None], [{"name_value": None}]]:
            client.get.return_value = payload
            self.assertEqual(CertificateProvider(client).collect(Query(QueryKind.DOMAIN, "example.com")).status, "error")


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.client = HttpClient(retries=1, interval=0)
        self.client._opener = Mock()
        self.response = Mock()
        self.response.__enter__ = Mock(return_value=self.response)
        self.response.__exit__ = Mock(return_value=False)
        self.response.read.return_value = b'{"ok":true}'
        self.url = "https://brasilapi.com.br/api/ddd/v1/11"

    @patch("amanhecer.http.time.sleep")
    def test_transient_error_is_retried(self, sleep):
        self.client._opener.open.side_effect = [HTTPError(self.url, 503, "unavailable", {}, None), self.response]
        self.assertEqual(self.client.get(self.url), {"ok": True})
        self.assertEqual(self.client._opener.open.call_count, 2)

    def test_404_is_not_retried(self):
        self.client._opener.open.side_effect = HTTPError(self.url, 404, "missing", {}, None)
        with self.assertRaisesRegex(SourceError, "404"):
            self.client.get(self.url)
        self.assertEqual(self.client._opener.open.call_count, 1)

    @patch("amanhecer.http.time.sleep")
    def test_network_attempts_are_bounded(self, sleep):
        self.client._opener.open.side_effect = URLError("offline")
        with self.assertRaises(SourceError):
            self.client.get(self.url)
        self.assertEqual(self.client._opener.open.call_count, 2)

    def test_invalid_json_and_size_limit(self):
        self.client._opener.open.return_value = self.response
        for body in [b'<html>bad gateway</html>', b'x' * 5_000_001]:
            self.response.read.return_value = body
            with self.assertRaises(SourceError):
                self.client.get(self.url)

    def test_untrusted_endpoint_rejected(self):
        for url in ["http://brasilapi.com.br", "https://localhost/", "https://brasilapi.com.br.evil.org/"]:
            with self.assertRaises(SourceError):
                self.client.get(url)
        self.client._opener.open.assert_not_called()


class CliReportTests(unittest.TestCase):
    def test_report_serialization_and_html_escape(self):
        report = Report(Query(QueryKind.CEP, "01001000"), [Evidence("test", "https://example.com", "ok", {"value": "<script>alert(1)</script>"})])
        self.assertEqual(json.loads(render_json(report))["query"]["kind"], "cep")
        self.assertNotIn("<script>", render_html(report))
        self.assertIn("&lt;script&gt;", render_html(report))

    @patch("amanhecer.cli.HttpClient")
    def test_invalid_input_does_not_create_client(self, client):
        with patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(main(["arroba", "@@apelido"]), 2)
        client.assert_not_called()

    @patch("amanhecer.cli.HttpClient")
    def test_cli_file_output_and_overwrite_protection(self, client):
        client.return_value.get.return_value = {"login": "octocat", "id": 1}
        target = Path(__file__).resolve().parent / f"report-{uuid4().hex}.json"
        try:
            with patch("sys.stderr", new=io.StringIO()):
                args = ["arroba", "@octocat", "--plataforma", "github", "--formato", "json", "--saida", str(target)]
                self.assertEqual(main(args), 0)
                self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["query"]["value"], "octocat")
                self.assertEqual(main(args), 2)
                client.return_value.get.assert_called_once()
        finally:
            target.unlink(missing_ok=True)

    @patch("amanhecer.cli.HttpClient")
    def test_cli_source_error_exit_code(self, client):
        client.return_value.get.side_effect = SourceError("offline")
        with patch("sys.stdout", new=io.StringIO()) as output:
            self.assertEqual(main(["arroba", "octocat", "--formato", "json"]), 1)
        self.assertEqual(json.loads(output.getvalue())["results"][0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
