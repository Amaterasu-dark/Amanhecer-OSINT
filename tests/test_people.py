"""Fixtures de CPF: dados fictícios publicados na demonstração oficial do Serpro."""
import io
import json
import os
from pathlib import Path
import tomllib
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from amanhecer import __version__
from amanhecer.application import InvestigationService
from amanhecer.cli import main
from amanhecer.cpf import CpfValidationProvider, SerproCpfProvider, birth_date
from amanhecer.domain import Query, QueryKind, Report
from amanhecer.http import HttpClient, NoRedirect
from amanhecer.names import GitHubNameProvider, GitLabNameProvider, name_providers
from amanhecer.ports import JsonResponse, SourceError, SourceHttpError
from amanhecer.reports import render_html, render_json, render_text


CPF = "40442820135"
BIRTH = "1970-11-14"
TOKEN = "synthetic-token-for-tests"


class PeopleInputTests(unittest.TestCase):
    def test_valid_cpf_with_and_without_formatting(self):
        self.assertEqual(Query(QueryKind.CPF, CPF).value, CPF)
        self.assertEqual(Query(QueryKind.CPF, "404.428.201-35").value, CPF)
        self.assertEqual(Query(QueryKind.CPF, "076.918.523-12").value, "07691852312")

    def test_invalid_cpf_never_becomes_a_query(self):
        for value in ["", "123", "00000000000", "11111111111", "40442820134", "404428201350", "cpf=" + CPF, "404/428/20135", "４０４４２８２０１３５"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                Query(QueryKind.CPF, value)

    def test_name_normalizes_spaces_and_unicode(self):
        self.assertEqual(Query(QueryKind.NAME, "  Joa\u0303o   D’Ávila-Silva  ").value, "João D’Ávila-Silva")
        self.assertEqual(Query(QueryKind.NAME, "李 小龙").value, "李 小龙")

    def test_name_rejects_query_injection_controls_and_single_words(self):
        for value in ["Maria", "João 123", 'Maria "Silva"', "Maria in:login", "João\nSilva", "João\x1bSilva", "João / Silva", "João - Silva", "A " + "b" * 120]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                Query(QueryKind.NAME, value)

    def test_birth_date_is_calendar_valid_and_formatted_for_serpro(self):
        self.assertEqual(birth_date(BIRTH), "14111970")
        self.assertEqual(birth_date("2000-02-29"), "29022000")
        for value in ["2001-02-29", "19701114", "14/11/1970", "1970-1-1", "9999-01-01"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                birth_date(value)


class CpfProviderTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.query = Query(QueryKind.CPF, CPF)
        self.provider = SerproCpfProvider(self.client, TOKEN, BIRTH)
        self.payload = {"ni": CPF, "nascimento": "14111970", "nome": "PESSOA FICTÍCIA", "situacao": {"codigo": "0", "descricao": "REGULAR"}}

    def test_local_validation_does_not_claim_lookup(self):
        result = CpfValidationProvider().collect(self.query)
        self.assertEqual(result.data["match"], "validated")
        self.assertIn("Nenhuma base cadastral", result.data["detail"])
        self.assertNotIn("record", result.data)

    def test_serpro_exact_request_and_minimal_result(self):
        self.client.get_response.return_value = JsonResponse(200, {**self.payload, "nomeSocial": "IGNORADO", "dataInscricao": "IGNORADA"})
        result = self.provider.collect(self.query)
        self.client.get_response.assert_called_once_with("https://gateway.apiserpro.serpro.gov.br/consulta-cpf-df/v3/cpf/40442820135/14111970", bearer_token=TOKEN)
        self.assertEqual(result.data["match"], "found")
        self.assertEqual(result.data["record"], {"name": "PESSOA FICTÍCIA", "registration_status": "REGULAR", "registration_status_code": "0"})
        self.assertNotIn(CPF, result.source_url)
        self.assertNotIn("14111970", result.source_url)

    def test_206_is_recorded_as_partial(self):
        self.client.get_response.return_value = JsonResponse(206, {"ni": CPF, "nascimento": "14111970", "nome": "PESSOA FICTÍCIA"})
        result = self.provider.collect(self.query)
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.data["partial"])
        self.assertIn("parcial", result.data["detail"])

    def test_wrong_identifiers_and_malformed_data_are_inconclusive(self):
        for payload in [None, [], {}, {**self.payload, "ni": "63017285995"}, {**self.payload, "nascimento": "01011970"}, {**self.payload, "nome": []}, {**self.payload, "situacao": {}}, {"ni": CPF, "nascimento": "14111970"}]:
            with self.subTest(payload=payload):
                self.client.get_response.return_value = JsonResponse(200, payload)
                result = self.provider.collect(self.query)
                self.assertEqual(result.status, "error")
                self.assertEqual(result.data["match"], "inconclusive")
                self.assertNotIn("record", result.data)

    def test_missing_birth_in_partial_response_is_inconclusive(self):
        self.client.get_response.return_value = JsonResponse(206, {"ni": CPF, "nome": "PESSOA FICTÍCIA"})
        self.assertEqual(self.provider.collect(self.query).data["match"], "inconclusive")

    def test_source_not_found_differs_from_access_failure(self):
        for code in [400, 401, 403, 404, 422, 429, 451, 500]:
            with self.subTest(code=code):
                self.client.get_response.side_effect = SourceHttpError(code)
                result = self.provider.collect(self.query)
                self.assertEqual(result.data["match"], "not_found" if code == 404 else "inconclusive")
                self.assertEqual(result.status, "ok" if code == 404 else "error")

    def test_reports_omit_cpf_birth_and_credentials(self):
        self.client.get_response.return_value = JsonResponse(200, self.payload)
        report = Report(self.query, [self.provider.collect(self.query)])
        for renderer in [render_text, render_json, render_html]:
            with self.subTest(renderer=renderer):
                output = renderer(report)
                for secret in [CPF, "404.428.201-35", BIRTH, "14111970", TOKEN]:
                    self.assertNotIn(secret, output)
                self.assertIn("***.***.***-35", output)
        self.assertEqual(report.query.value, CPF)

    def test_untrusted_error_details_are_not_copied_into_cpf_report(self):
        self.client.get_response.side_effect = SourceError(CPF + TOKEN)
        output = render_json(Report(self.query, [self.provider.collect(self.query)]))
        self.assertNotIn(CPF, output)
        self.assertNotIn(TOKEN, output)


class NameProviderTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.query = Query(QueryKind.NAME, "Maria da Silva")

    def test_github_search_query_candidates_and_bounds(self):
        self.client.get.return_value = {"items": [{"login": "maria", "html_url": "javascript:bad"}], "total_count": 11, "incomplete_results": False}
        result = GitHubNameProvider(self.client, 10).collect(self.query)
        params = parse_qs(urlsplit(self.client.get.call_args.args[0]).query)
        self.assertEqual(params["q"], ['"Maria da Silva" in:fullname type:user'])
        self.assertEqual(params["per_page"], ["10"])
        self.assertEqual(result.data["match"], "candidates")
        self.assertTrue(result.data["more_results_possible"])
        self.assertEqual(result.data["candidates"][0]["profile_url"], "https://github.com/maria")
        self.assertFalse(result.data["candidates"][0]["identity_confirmed"])
        self.assertNotIn("display_name", result.data["candidates"][0])

    def test_gitlab_search_is_marked_as_candidates_and_deduplicated(self):
        self.client.get.return_value = [{"username": "maria", "name": "Maria Silva"}, {"username": "MARIA", "name": "Maria Silva"}]
        result = GitLabNameProvider(self.client, 2).collect(self.query)
        self.assertEqual(len(result.data["candidates"]), 1)
        self.assertEqual(result.data["match"], "candidates")
        self.assertTrue(result.data["more_results_possible"])
        self.assertIn("homônimos", result.data["note"])

    def test_empty_complete_and_incomplete_searches_are_distinct(self):
        for incomplete, expected in [(False, "not_found"), (True, "inconclusive")]:
            self.client.get.return_value = {"items": [], "total_count": 0, "incomplete_results": incomplete}
            result = GitHubNameProvider(self.client).collect(self.query)
            self.assertEqual(result.data["match"], expected)
            self.assertEqual(result.status, "error" if incomplete else "ok")

    def test_incomplete_search_keeps_returned_candidates(self):
        self.client.get.return_value = {"items": [{"login": "maria"}], "total_count": 1, "incomplete_results": True}
        result = GitHubNameProvider(self.client).collect(self.query)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.data["match"], "candidates")
        self.assertEqual(len(result.data["candidates"]), 1)

    def test_bad_search_response_does_not_become_a_match(self):
        for payload in [{}, {"items": [], "total_count": True, "incomplete_results": False}, {"items": [{"login": "../evil"}], "total_count": 1, "incomplete_results": False}, {"items": [], "total_count": 0, "incomplete_results": "false"}]:
            with self.subTest(payload=payload):
                self.client.get.return_value = payload
                self.assertEqual(GitHubNameProvider(self.client).collect(self.query).data["match"], "inconclusive")
        for payload in [{}, [None], [{"username": "a", "name": []}], [{"username": "a"}, {"username": "b"}]]:
            with self.subTest(payload=payload):
                self.client.get.return_value = payload
                self.assertEqual(GitLabNameProvider(self.client, 1).collect(self.query).data["match"], "inconclusive")

    def test_partial_failure_and_platform_selection(self):
        self.client.get.side_effect = [SourceHttpError(403), [{"username": "maria"}]]
        report = InvestigationService(name_providers(self.client)).investigate(self.query)
        self.assertEqual([r.status for r in report.results], ["error", "ok"])
        self.assertEqual(len(name_providers(self.client, ["github", "github"])), 1)


class PeopleCliTests(unittest.TestCase):
    @patch("amanhecer.cli.HttpClient")
    def test_cpf_offline_uses_no_network_and_has_explicit_label(self, client):
        with patch("sys.stdout", new=io.StringIO()) as output:
            self.assertEqual(main(["cpf", CPF, "--somente-validar"]), 0)
        client.assert_not_called()
        self.assertIn("[DÍGITOS VÁLIDOS]", output.getvalue())
        self.assertNotIn(CPF, output.getvalue())
        self.assertNotIn("[ENCONTRADO]", output.getvalue())

    @patch("amanhecer.cli.HttpClient")
    def test_cpf_missing_configuration_stops_before_network(self, client):
        with patch.dict(os.environ, {}, clear=True), patch("sys.stderr", new=io.StringIO()) as error:
            self.assertEqual(main(["cpf", CPF]), 2)
            self.assertEqual(main(["cpf", CPF, "--nascimento", BIRTH]), 2)
        client.assert_not_called()
        self.assertIn("AMANHECER_SERPRO_TOKEN", error.getvalue())
        self.assertNotIn(CPF, error.getvalue())

    @patch("amanhecer.cli.HttpClient")
    def test_cpf_configured_query_disables_retries(self, client):
        client.return_value.get_response.return_value = JsonResponse(200, {"ni": CPF, "nascimento": "14111970", "nome": "PESSOA FICTÍCIA", "situacao": {"codigo": "0", "descricao": "REGULAR"}})
        with patch.dict(os.environ, {"AMANHECER_SERPRO_TOKEN": TOKEN}), patch("sys.stdout", new=io.StringIO()) as output:
            self.assertEqual(main(["cpf", CPF, "--nascimento", BIRTH, "--formato", "json"]), 0)
        client.assert_called_once_with(timeout=15, retries=0)
        self.assertEqual(json.loads(output.getvalue())["results"][0]["data"]["record"]["registration_status"], "REGULAR")

    @patch("amanhecer.cli.HttpClient")
    def test_name_command_displays_candidates(self, client):
        client.return_value.get.return_value = [{"username": "maria", "name": "Maria Silva"}]
        with patch("sys.stdout", new=io.StringIO()) as output:
            self.assertEqual(main(["nome", "Maria da Silva", "--plataforma", "gitlab", "--limite", "5"]), 0)
        self.assertIn("[CANDIDATOS]", output.getvalue())
        self.assertIn("https://gitlab.com/maria", output.getvalue())
        self.assertIn("homônimos", output.getvalue())

    @patch("amanhecer.cli.HttpClient")
    def test_invalid_option_combinations_stop_before_network(self, client):
        cases = [["arroba", "user", "--nascimento", BIRTH], ["nome", "Maria Silva", "--somente-validar"], ["arroba", "user", "--limite", "5"], ["cpf", CPF, "--plataforma", "github"], ["nome", "Maria Silva", "--limite", "0"], ["nome", "Maria Silva", "--limite", "51"], ["cpf", CPF, "--nascimento", "2001-02-29"], ["cpf", CPF, "--somente-validar", "--nascimento", BIRTH]]
        for args in cases:
            with self.subTest(args=args), patch("sys.stderr", new=io.StringIO()):
                self.assertEqual(main(args), 2)
        client.assert_not_called()

    def test_version_matches_package_metadata(self):
        metadata = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["version"], __version__)
        with patch("sys.stdout", new=io.StringIO()) as output, self.assertRaises(SystemExit) as raised:
            main(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn(__version__, output.getvalue())


class AuthorizedTransportTests(unittest.TestCase):
    def test_bearer_token_is_restricted_to_serpro_query_endpoint(self):
        client = HttpClient(retries=0, interval=0)
        client._opener = Mock()
        for url in ["https://api.github.com/users/octocat", "https://gitlab.com/api/v4/users", "https://gateway.apiserpro.serpro.gov.br/token", "http://gateway.apiserpro.serpro.gov.br/consulta-cpf-df/v3/cpf/a/b"]:
            with self.subTest(url=url), self.assertRaises(SourceError):
                client.get_response(url, bearer_token=TOKEN)
        client._opener.open.assert_not_called()

    def test_status_code_and_bearer_reach_only_authorized_request(self):
        client = HttpClient(retries=0, interval=0)
        client._opener = Mock()
        response = Mock(status=206)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{}'
        client._opener.open.return_value = response
        result = client.get_response("https://gateway.apiserpro.serpro.gov.br/consulta-cpf-df/v3/cpf/40442820135/14111970", bearer_token=TOKEN)
        self.assertEqual(result.status_code, 206)
        self.assertEqual(client._opener.open.call_args.args[0].get_header("Authorization"), "Bearer " + TOKEN)
        client.get("https://api.github.com/users/octocat")
        self.assertIsNone(client._opener.open.call_args.args[0].get_header("Authorization"))

    def test_invalid_token_and_redirect_never_leak_credentials(self):
        client = HttpClient(retries=0, interval=0)
        client._opener = Mock()
        url = "https://gateway.apiserpro.serpro.gov.br/consulta-cpf-df/v3/cpf/40442820135/14111970"
        for token in ["", "a\r\nInjected: true", "a b"]:
            with self.subTest(token=token), self.assertRaises(SourceError):
                client.get_response(url, bearer_token=token)
        client._opener.open.assert_not_called()
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://example.com"))
        client._opener.open.side_effect = HTTPError(url, 302, "Found", {"Location": "https://example.com"}, None)
        with self.assertRaises(SourceHttpError):
            client.get_response(url, bearer_token=TOKEN)
        client._opener.open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
