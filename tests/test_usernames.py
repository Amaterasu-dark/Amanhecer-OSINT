import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from amanhecer.application import InvestigationService
from amanhecer.cli import main
from amanhecer.domain import Evidence, Query, QueryKind, Report
from amanhecer.http import HttpClient
from amanhecer.ports import SourceError, SourceHttpError
from amanhecer.providers import default_providers, legacy_providers
from amanhecer.reports import render_html, render_text
from amanhecer.usernames import GitHubUsernameProvider, GitLabUsernameProvider


class UsernameTests(unittest.TestCase):
    def test_optional_at_and_case_preserved(self):
        for value in ["OctoCat", "@OctoCat", "  @OctoCat  "]:
            self.assertEqual(Query(QueryKind.USERNAME, value).value, "OctoCat")
        self.assertEqual(Query(QueryKind.USERNAME, "@nome.sobrenome_1-2").value, "nome.sobrenome_1-2")

    def test_rejects_urls_paths_extra_at_whitespace_and_controls(self):
        for value in ["", "@", "@@user", "a@b", "nome completo", "https://github.com/user", "a/b", "a?b", "a#b", "a\nb", "a\x1bb", "a" * 65, "..", "-x", "joão"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                Query(QueryKind.USERNAME, value)

    def test_old_sources_do_not_receive_username_queries(self):
        query = Query(QueryKind.USERNAME, "octocat")
        self.assertFalse(any(p.supports(query) for p in legacy_providers(Mock())))
        self.assertTrue(all(p.supports(query) for p in default_providers(Mock())))
        self.assertFalse(any(p.supports(Query(QueryKind.DOMAIN, "example.com")) for p in default_providers(Mock())))


class UsernameProviderTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.query = Query(QueryKind.USERNAME, "@OctoCat")

    def test_github_exact_match_and_public_fields(self):
        self.client.get.return_value = {"login": "octocat", "id": 1, "name": "The Octocat", "type": "User", "email": "ignored@example.com", "private_repos": 12, "html_url": "javascript:bad"}
        result = GitHubUsernameProvider(self.client).collect(self.query)
        self.client.get.assert_called_once_with("https://api.github.com/users/OctoCat")
        self.assertEqual(result.data["match"], "found")
        self.assertEqual(result.data["profile"]["profile_url"], "https://github.com/octocat")
        self.assertEqual(result.data["profile"]["display_name"], "The Octocat")
        self.assertNotIn("email", result.data["profile"])
        self.assertNotIn("private_repos", result.data["profile"])
        self.assertTrue(result.collected_at.endswith("+00:00"))

    def test_github_404_means_no_public_profile_returned(self):
        self.client.get.side_effect = SourceHttpError(404)
        result = GitHubUsernameProvider(self.client).collect(self.query)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["match"], "not_found")
        self.assertNotIn("profile", result.data)

    def test_blocked_redirect_rate_limit_and_network_are_inconclusive(self):
        for error in [SourceHttpError(301), SourceHttpError(401), SourceHttpError(403), SourceHttpError(429), SourceHttpError(503), SourceError("offline")]:
            with self.subTest(error=error):
                self.client.get.side_effect = error
                result = GitHubUsernameProvider(self.client).collect(self.query)
                self.assertEqual(result.status, "error")
                self.assertEqual(result.data["match"], "inconclusive")

    def test_github_wrong_handle_and_malformed_payload_are_inconclusive(self):
        for payload in [{}, [], None, {"login": "someone-else"}, {"login": 3}, {"login": "octocat", "bio": {"bad": "data"}}]:
            with self.subTest(payload=payload):
                self.client.get.return_value = payload
                result = GitHubUsernameProvider(self.client).collect(self.query)
                self.assertEqual(result.data["match"], "inconclusive")

    def test_gitlab_exact_match_and_empty_result(self):
        self.client.get.return_value = [{"username": "octocat", "id": 2, "name": "Example"}]
        result = GitLabUsernameProvider(self.client).collect(self.query)
        self.client.get.assert_called_once_with("https://gitlab.com/api/v4/users?username=OctoCat")
        self.assertEqual(result.data["match"], "found")
        self.assertEqual(result.data["profile"]["profile_url"], "https://gitlab.com/octocat")
        self.client.get.return_value = []
        self.assertEqual(GitLabUsernameProvider(self.client).collect(self.query).data["match"], "not_found")

    def test_gitlab_does_not_accept_approximate_or_ambiguous_matches(self):
        for payload in [{}, [None], [{"username": 1}], [{"username": "octocat2"}], [{"username": "octocat"}, {"username": "octocat"}]]:
            with self.subTest(payload=payload):
                self.client.get.return_value = payload
                result = GitLabUsernameProvider(self.client).collect(self.query)
                self.assertEqual(result.data["match"], "inconclusive")

    def test_gitlab_404_is_a_source_failure_not_an_empty_result(self):
        self.client.get.side_effect = SourceHttpError(404)
        self.assertEqual(GitLabUsernameProvider(self.client).collect(self.query).data["match"], "inconclusive")

    def test_one_failed_platform_keeps_other_results(self):
        self.client.get.side_effect = [SourceHttpError(403), [{"username": "octocat", "id": 2}]]
        report = InvestigationService(default_providers(self.client)).investigate(self.query)
        self.assertEqual([r.data["match"] for r in report.results], ["inconclusive", "found"])

    def test_duplicate_platform_requested_once(self):
        providers = default_providers(self.client, ["github", "github"])
        self.assertEqual([p.name for p in providers], ["GitHub"])


class UsernameCliTests(unittest.TestCase):
    @patch("amanhecer.cli.HttpClient")
    def test_text_output_is_default_and_platform_selects_one_source(self, client):
        client.return_value.get.return_value = {"login": "octocat", "id": 1, "name": "Octocat"}
        with patch("sys.stdout", new=io.StringIO()) as output:
            self.assertEqual(main(["arroba", "@octocat", "--plataforma", "github"]), 0)
        self.assertIn("[ENCONTRADO] GitHub", output.getvalue())
        self.assertIn("https://github.com/octocat", output.getvalue())
        client.return_value.get.assert_called_once()

    @patch("amanhecer.cli.HttpClient")
    def test_json_partial_failure_exit_code_and_evidence(self, client):
        client.return_value.get.side_effect = [SourceHttpError(429), []]
        with patch("sys.stdout", new=io.StringIO()) as output:
            self.assertEqual(main(["arroba", "octocat", "--formato", "json"]), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["query"], {"kind": "arroba", "value": "octocat"})
        self.assertEqual([r["data"]["match"] for r in report["results"]], ["inconclusive", "not_found"])

    @patch("amanhecer.cli.HttpClient")
    def test_no_public_match_is_a_successful_lookup(self, client):
        client.return_value.get.side_effect = SourceHttpError(404)
        with patch("sys.stdout", new=io.StringIO()) as output:
            self.assertEqual(main(["arroba", "octocat", "--plataforma", "github"]), 0)
        self.assertIn("[NÃO ENCONTRADO]", output.getvalue())

    @patch("amanhecer.cli.HttpClient")
    def test_out_of_scope_commands_fail_before_network(self, client):
        for kind in ["dominio", "cep", "ddd", "banco"]:
            with self.subTest(kind=kind), patch("sys.stderr", new=io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main([kind, "example"])
                self.assertEqual(raised.exception.code, 2)
        client.assert_not_called()

    @patch("amanhecer.cli.HttpClient")
    def test_cnpj_and_phone_local_commands_do_not_create_client(self, client):
        for kind, value, expected in [("cnpj", "00.000.000/0001-91", "validated"),
                                      ("telefone", "(11) 91234-5678", "format_valid")]:
            with self.subTest(kind=kind), patch("sys.stdout", new=io.StringIO()) as output:
                self.assertEqual(main([kind, value, "--somente-validar", "--formato", "json"]), 0)
                self.assertEqual(json.loads(output.getvalue())["results"][0]["data"]["match"], expected)
        client.assert_not_called()

    def test_external_content_is_safe_in_terminal_and_html(self):
        bio = "\x1b[2J\n[ENCONTRADO] falso\u202e<script>alert(1)</script>"
        report = Report(Query(QueryKind.USERNAME, "octocat"), [Evidence("GitHub", "https://api.github.com/users/octocat", "ok", {"match": "found", "profile": {"bio": bio}})])
        output = render_text(report)
        self.assertNotIn("\x1b", output)
        self.assertNotIn("\u202e", output)
        self.assertNotIn("\n[ENCONTRADO] falso", output)
        self.assertNotIn("<script>", render_html(report))


class UsernameHttpTests(unittest.TestCase):
    def test_rate_limit_is_not_retried(self):
        client = HttpClient(retries=2, interval=0)
        client._opener = Mock()
        url = "https://api.github.com/users/octocat"
        client._opener.open.side_effect = HTTPError(url, 429, "rate limit", {}, None)
        with self.assertRaises(SourceHttpError) as raised:
            client.get(url)
        self.assertEqual(raised.exception.status_code, 429)
        client._opener.open.assert_called_once()

    def test_http_status_reaches_provider(self):
        client = HttpClient(retries=0, interval=0)
        client._opener = Mock()
        url = "https://api.github.com/users/octocat"
        client._opener.open.side_effect = HTTPError(url, 404, "missing", {}, None)
        with self.assertRaises(SourceHttpError) as raised:
            client.get(url)
        self.assertEqual(raised.exception.status_code, 404)

    def test_github_headers_and_gitlab_requests(self):
        client = HttpClient(retries=0, interval=0)
        client._opener = Mock()
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{}'
        client._opener.open.return_value = response
        client.get("https://api.github.com/users/octocat")
        request = client._opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Accept"), "application/vnd.github+json")
        self.assertEqual(request.get_header("X-github-api-version"), "2026-03-10")
        client.get("https://gitlab.com/api/v4/users?username=octocat")
        request = client._opener.open.call_args.args[0]
        self.assertIsNone(request.get_header("X-github-api-version"))


if __name__ == "__main__":
    unittest.main()
