import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run


class CollectorTests(unittest.TestCase):
    def test_doi_normalization(self):
        self.assertEqual(run.normal_doi("https://doi.org/10.1111/AB-123."), "10.1111/ab-123")
        self.assertEqual(run.normal_doi("not a DOI"), "")

    def test_source_exact_match(self):
        class Stub:
            def request(self, *_args, **_kwargs):
                return {"results": [
                    {"display_name": "Learning and Instruction", "type": "journal", "id": "https://openalex.org/S42"},
                    {"display_name": "Instructional Learning", "type": "journal", "id": "https://openalex.org/S43"}
                ]}
        self.assertEqual(run.fetch_source(Stub(), "Learning and Instruction")["id"], "https://openalex.org/S42")
        self.assertIsNone(run.fetch_source(Stub(), "Nonexistent Journal"))

    def test_records_and_merge(self):
        work = {"id": "https://openalex.org/W77", "doi": "https://doi.org/10.5555/sample", "display_name": "Sample learning study", "publication_year": 2024,
                "type": "article", "primary_location": {"source": {"display_name": "Sample Journal"}},
                "open_access": {"oa_status": "green"},
                "best_oa_location": {"is_oa": True, "pdf_url": "https://example.edu/sample.pdf", "license": "cc-by", "landing_page_url": "https://example.edu/item"},
                "abstract_inverted_index": {"Learning": [0], "matters": [1]}}
        a = run.make_record(work, "Education", "learning")
        b = run.make_record(work, "Education", "teachers")
        self.assertEqual(a["abstract"], "Learning matters")
        self.assertEqual(a["is_oa"], "yes")
        run.merge_record(a, b)
        self.assertEqual(a["matched_topics"], "learning | teachers")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.csv"
            run.write_csv(path, [a], run.FIELDS)
            self.assertTrue(path.read_text(encoding="utf-8-sig").startswith("record_id,title"))
            run.write_ris([a], Path(tmp) / "sample.ris")
            self.assertIn("DO  - 10.5555/sample", (Path(tmp) / "sample.ris").read_text())

    def test_pdf_only_if_real_pdf_and_oa(self):
        class FakeHTTP:
            def __init__(self, binary):
                self.binary = binary
            def request(self, *_args, **_kwargs):
                return (self.binary, "https://repo.example.edu/p.pdf", "application/pdf")
        with tempfile.TemporaryDirectory() as d:
            rec = {"is_oa": "yes", "pdf_url": "https://repo.example.edu/p.pdf", "doi": "10.5555/test"}
            self.assertEqual(run.download_pdf(FakeHTTP(b"<html>Denied</html>"), rec, Path(d), 10), "response_not_pdf")
            self.assertFalse(list(Path(d).glob("*.pdf")))
            self.assertEqual(run.download_pdf(FakeHTTP(b"%PDF-1.7\nexample"), rec, Path(d), 10), "downloaded")
            self.assertTrue(list(Path(d).glob("*.pdf")))



# Tests added in v2 are defined separately so the existing suite stays intact.
class StrictFreePDFTests(unittest.TestCase):
    def test_collects_alternative_university_repository_pdf(self):
        work = {
            "id": "https://openalex.org/W9", "display_name": "Teacher collaboration evidence", "doi": "https://doi.org/10.1111/demo",
            "open_access": {"is_oa": True, "oa_status": "green"},
            "best_oa_location": {"is_oa": True, "landing_page_url": "https://publisher.example/paper", "pdf_url": None, "source": {"type": "journal"}},
            "locations": [{"is_oa": True, "pdf_url": "https://university.edu/open-research/paper.pdf", "source": {"display_name": "Example University Institutional Repository", "type": "repository"}, "version": "acceptedVersion"}]
        }
        r = run.make_record(work)
        self.assertEqual(len(r["_pdf_candidates"]), 1)
        self.assertEqual(r["_pdf_candidates"][0]["source_type"], "repository")
        self.assertEqual(r["_pdf_candidates"][0]["url"], "https://university.edu/open-research/paper.pdf")

    def test_no_html_paywall_claimed_verified(self):
        from unittest.mock import patch
        class Response:
            headers = {"Content-Type": "text/html"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return "https://journal.example/paywall"
            def read(self, _n): return b"<html>Subscribe to read full text</html>"
        class Client:
            cfg = {"request_delay_seconds": 0, "request_timeout_seconds": 2}
            last_request = 0
            ua = "Test/1.0"
            email = ""
        with patch.object(run, "urlopen", return_value=Response()):
            ok, final, status = run.probe_pdf_link(Client(), "https://journal.example/pdf.pdf")
        self.assertFalse(ok)
        self.assertEqual(final, "")
        self.assertEqual(status, "returned_html_or_non_pdf")

    def test_verified_pdf_link_is_retained_without_full_download(self):
        from unittest.mock import patch
        class Client:
            email = ""
        r = {"is_oa": "yes", "doi": "10.1111/demo", "_pdf_candidates": [
            {"url": "https://open.edu/article.pdf", "source": "University Repository", "source_type": "repository", "version": "acceptedVersion", "landing": "https://open.edu/records/demo", "license": "", "method": "OpenAlex OA location"}
        ]}
        with patch.object(run, "probe_pdf_link", return_value=(True,"https://open.edu/article.pdf","verified_pdf_header")):
            self.assertTrue(run.verify_free_pdf_links(Client(), r, {"max_pdf_candidates_per_record": 5}, download_enabled=False))
        self.assertEqual(r["verified_pdf_url"], "https://open.edu/article.pdf")
        self.assertEqual(r["pdf_status"], "verified_link_not_saved")
        self.assertEqual(r["pdf_source_type"], "repository")

    def test_unverified_link_excluded(self):
        from unittest.mock import patch
        class Client:
            email = ""
        r = {"doi": "10.1111/demo", "_pdf_candidates": [
            {"url": "https://publisher.edu/no.pdf", "source": "Publisher", "source_type": "journal", "version": "", "landing": "", "license": "", "method": "OpenAlex OA location"}
        ]}
        with patch.object(run, "probe_pdf_link", return_value=(False, "", "http_403")):
            self.assertFalse(run.verify_free_pdf_links(Client(), r, {"max_pdf_candidates_per_record": 5}))
        self.assertEqual(r["verified_pdf_url"], "")
        self.assertIn("http_403", r["pdf_link_status"])

    def test_scopus_wos_csv_and_ris_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"scopus.csv"
            path.write_text('Title,DOI,Authors\n"Paper 1",10.1111/ABC,"J. Smith"\n"Paper 2",https://doi.org/10.1234/Z-1,"X. Doe"\n', encoding="utf-8")
            valid, invalid = run.read_doi_inputs(path)
            self.assertEqual(valid, ["10.1111/abc", "10.1234/z-1"])
            self.assertEqual(invalid, [])
            wos = Path(tmp)/"wos.tsv"
            wos.write_text('Title\tDI\nPaper\t10.1111/xyz\n',encoding="utf-8")
            self.assertEqual(run.read_doi_inputs(wos)[0], ["10.1111/xyz"])
            ris = Path(tmp)/"wos.ris"
            ris.write_text('TY  - JOUR\nDO  - 10.1111/foo\nER  - \n', encoding="utf-8")
            self.assertEqual(run.read_doi_inputs(ris)[0], ["10.1111/foo"])

    def test_formal_exports_contain_only_verified_links(self):
        from unittest.mock import patch
        import csv
        class Client:
            email = ""
        def checked(_client, rec, _cfg, download_enabled=False):
            if rec["record_id"] == "good":
                rec["verified_pdf_url"] = "https://university.example/good.pdf"
                rec["pdf_source"] = "University Repository"
                rec["pdf_link_status"] = "verified_pdf_header"
                rec["pdf_status"] = "verified_link_not_saved"
                return True
            rec["verified_pdf_url"] = ""
            rec["pdf_status"] = "not_downloaded_no_verified_link"
            return False
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"download_open_access_pdfs": True, "max_pdf_downloads": 2,
                   "verify_doi_with_crossref": False, "require_verified_free_pdf": True,
                   "max_results_per_topic_journal": 10, "max_total_records": 20,
                   "year_from": 2022, "year_to": 2026}
            rows = [{"record_id": "good", "title": "Paper has free PDF", "doi": "10.1234/good"},
                    {"record_id": "bad", "title": "Paywall paper", "doi": "10.1234/bad"}]
            with patch.object(run, "BASE", Path(tmp)), \
                 patch.object(run, "read_config", return_value=(cfg, [{"journal": "Test"}])), \
                 patch.object(run, "HTTPClient", return_value=Client()), \
                 patch.object(run, "search_records", return_value=(rows, [])), \
                 patch.object(run, "verify_free_pdf_links", side_effect=checked), \
                 patch.object(sys, "argv", ["run.py", "--no-pdf"]):
                run.main()
            out = Path(tmp) / "output"
            with (out / "verified_free_pdf_results.csv").open(encoding="utf-8-sig", newline="") as f:
                good = list(csv.DictReader(f))
            with (out / "all_results.csv").open(encoding="utf-8-sig", newline="") as f:
                official = list(csv.DictReader(f))
            with (out / "needs_manual_access.csv").open(encoding="utf-8-sig", newline="") as f:
                rejected = list(csv.DictReader(f))
            self.assertEqual(len(good), 1)
            self.assertEqual(len(official), 1)
            self.assertEqual(len(rejected), 1)
            self.assertEqual(good[0]["verified_pdf_url"], "https://university.example/good.pdf")
            self.assertEqual(rejected[0]["record_id"], "bad")
            self.assertEqual((out / "references.ris").read_text().count("TY  - JOUR"), 1)


if __name__ == "__main__":
    unittest.main()
