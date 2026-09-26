import json
import unittest
from dataclasses import replace

from amanhecer.core.models import Evidence, Query, QueryKind, Report
from amanhecer.reporting.renderers import render_html, render_json, render_text


class DeduplicationTests(unittest.TestCase):
    def candidate(self, username="maria", host="github.com"):
        return {"username": username, "profile_url": f"https://{host}/{username}",
                "display_name": "Maria Silva", "identity_confirmed": False}

    def evidence(self, candidates=None):
        return Evidence("GitHub — nome", "https://api.github.com/search/users", "ok",
                        {"match": "candidates", "candidates": candidates or [self.candidate()],
                         "more_results_possible": True, "total_reported": 20})

    def report(self, results):
        return Report(Query(QueryKind.NAME, "Maria Silva"), results)

    def test_repeated_evidence_ignores_timestamp_and_keeps_first(self):
        first = self.evidence()
        duplicate = replace(first, collected_at="2026-09-25T00:00:00+00:00")
        report = self.report([first, duplicate])
        self.assertEqual(len(report.results), 1)
        self.assertEqual(report.results[0].collected_at, first.collected_at)

    def test_candidates_are_unique_without_mutating_input(self):
        candidates = [self.candidate(), self.candidate("MARIA"), self.candidate("outra")]
        candidates[1]["profile_url"] += "/"
        result = self.evidence(candidates)
        self.assertEqual([c["username"] for c in result.data["candidates"]], ["maria", "outra"])
        self.assertEqual(len(candidates), 3)
        self.assertEqual(result.data["total_reported"], 20)
        self.assertTrue(result.data["more_results_possible"])

    def test_same_name_or_username_on_different_platforms_is_preserved(self):
        result = self.evidence([self.candidate(), self.candidate(host="gitlab.com"),
                                self.candidate("outra")])
        self.assertEqual(len(result.data["candidates"]), 3)
        report = self.report([result, replace(result, provider="Outra fonte")])
        self.assertEqual(len(report.results), 2)

    def test_errors_and_different_data_or_sources_are_preserved(self):
        first = self.evidence()
        results = [first, replace(first, status="error", error="Pesquisa incompleta"),
                   replace(first, source_url="https://api.github.com/search/users?page=2"),
                   self.evidence([self.candidate("outra")])]
        self.assertEqual(len(self.report(results).results), 4)

    def test_all_formats_revalidate_late_duplicates(self):
        report = self.report([self.evidence()])
        report.results[0].data["candidates"].append(self.candidate("MARIA"))
        report.results.append(replace(report.results[0]))
        text = render_text(report)
        data = json.loads(render_json(report))
        html = render_html(report)
        self.assertEqual(text.count("[CANDIDATOS]"), 1)
        self.assertEqual(text.count("(@maria)"), 1)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(len(data["results"][0]["data"]["candidates"]), 1)
        self.assertEqual(html.count("https://github.com/maria"), 1)


if __name__ == "__main__":
    unittest.main()
