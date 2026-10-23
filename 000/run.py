#!/usr/bin/env python3
"""Education OA literature collector using OpenAlex & optional Crossref.

No bypass of paywalls, login-only resources, CAPTCHAs or robots restrictions.
Standard library only. Run `python run.py --check` to verify configuration.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
FIELDS = ["record_id", "title", "authors", "year", "publication_date", "journal", "journal_field", "doi", "doi_url", "doi_verification", "publication_type", "matched_topics", "oa_status", "is_oa", "oa_license", "oa_version", "pdf_url", "oa_landing_url", "publisher_url", "openalex_id", "cited_by_count", "abstract", "pdf_status", "pdf_file", "verified_pdf_url", "pdf_link_status", "pdf_link_checked_at_utc", "pdf_source", "pdf_source_type", "pdf_version", "pdf_repository_landing_url", "pdf_candidates_checked", "pdf_access_method", "retrieved_at_utc"]


def clean(s):
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKC", str(s or "")).lower())


def normal_doi(doi):
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(doi or "").strip(), flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I).strip().rstrip(". ,;")
    return doi.lower() if re.match(r"^10\.\d{4,9}/\S+$", doi, re.I) else ""


def read_config():
    cfg = json.loads((BASE / "config/settings.json").read_text(encoding="utf-8"))
    with (BASE / "config/journals.csv").open(encoding="utf-8-sig", newline="") as f:
        journals = [row for row in csv.DictReader(f) if row.get("include", "yes").strip().lower() in ("yes", "1", "true", "y")]
    if not journals:
        raise ValueError("journal list empty: enable at least one in config/journals.csv")
    if cfg.get("require_verified_free_pdf") is not True:
        raise ValueError("Strict verified free PDF mode must remain true")
    if not cfg.get("search_keywords"):
        raise ValueError("search_keywords empty: edit config/settings.json")
    if int(cfg["year_from"]) > int(cfg["year_to"]):
        raise ValueError("year_from > year_to")
    if not 1 <= int(cfg["max_results_per_topic_journal"]) <= 100:
        raise ValueError("max_results_per_topic_journal must be 1..100")
    if int(cfg["max_total_records"]) < 1 or int(cfg["max_pdf_downloads"]) < 0 or int(cfg.get("max_pdf_candidates_per_record", 15)) < 1:
        raise ValueError("Invalid result/download limits")
    return cfg, journals


class HTTPClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.last_request = 0.0
        self.key = os.environ.get("OPENALEX_API_KEY", "").strip()
        self.email = os.environ.get("SCHOLAR_EMAIL", "").strip()
        self.ua = "EducationResearchCollector/2.0 (+https://www.crossref.org/documentation/retrieve-metadata/rest-api/)"
        if self.email:
            self.ua += " mailto:" + self.email

    def request(self, url, params=None, binary=False, size_limit=None):
        if params:
            params = dict(params)
            if url.startswith("https://api.openalex.org/") and self.key:
                params["api_key"] = self.key
            if url.startswith("https://api.crossref.org/") and self.email:
                params["mailto"] = self.email
            url += ("&" if "?" in url else "?") + urlencode(params)
        delay = float(self.cfg.get("request_delay_seconds", 0.35))
        for attempt in range(3):
            pause = delay - (time.monotonic() - self.last_request)
            if pause > 0:
                time.sleep(pause)
            self.last_request = time.monotonic()
            headers = {"User-Agent": self.ua, "Accept": "*/*" if binary else "application/json"}
            req = Request(url, headers=headers)
            try:
                with urlopen(req, timeout=float(self.cfg.get("request_timeout_seconds", 22))) as r:
                    if binary:
                        max_size = size_limit or 25 * 1024 * 1024
                        declared = r.headers.get("Content-Length")
                        if declared and int(declared) > max_size:
                            raise ValueError("PDF exceeds size limit")
                        data = r.read(max_size + 1)
                        if len(data) > max_size:
                            raise ValueError("PDF exceeds size limit")
                        return data, r.geturl(), r.headers.get("Content-Type", "")
                    return json.loads(r.read().decode("utf-8"))
            except HTTPError as e:
                if e.code == 404:
                    return None
                if e.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise RuntimeError(f"HTTP {e.code} from {urlsplit(url).netloc}: {str(e)[:140]}") from e
                try:
                    backoff = min(15, float(e.headers.get("Retry-After", "2")))
                except (ValueError, TypeError):
                    backoff = 2
                time.sleep(max(1.0, backoff) * (attempt + 1))
            except (URLError, TimeoutError) as e:
                if attempt == 2:
                    raise RuntimeError(f"Network error from {urlsplit(url).netloc}: {e}") from e
                time.sleep(1 + attempt * 2)


def fetch_source(client, journal):
    obj = client.request("https://api.openalex.org/sources", {"search": journal, "per_page": 20}) or {}
    results = obj.get("results", [])
    exact = [v for v in results if clean(v.get("display_name")) == clean(journal) and v.get("type") == "journal"]
    if len(exact) == 1:
        return exact[0]
    # Deliberately avoid guessing when there is no unique title match.
    return None


def get_abstract(inv):
    if not isinstance(inv, dict):
        return ""
    positions = {}
    for word, spots in inv.items():
        for n in spots:
            if isinstance(n, int) and n >= 0 and n < 10000:
                positions[n] = word
    return " ".join(positions[n] for n in sorted(positions))


def best_oa(work):
    loc = work.get("best_oa_location") or {}
    return loc if loc.get("is_oa") else {}


def pdf_candidates_from_work(work):
    """All declared OA host copies, not only the best location.

    University/subject repositories and publisher PDFs are both eligible;
    never infer a PDF URL from an abstract, DOI, or landing page.
    """
    locations = [work.get("best_oa_location"), *(work.get("locations") or []), work.get("primary_location")]
    output, seen = [], set()
    for loc in locations:
        if not isinstance(loc, dict) or not loc.get("is_oa"):
            continue
        url = str(loc.get("pdf_url") or "").strip()
        if not url.lower().startswith("https://") or url in seen:
            continue
        seen.add(url)
        src = loc.get("source") or {}
        output.append({
            "url": url,
            "source": src.get("display_name") or "Unspecified OA host",
            "source_type": src.get("type") or "unknown",
            "version": loc.get("version") or "",
            "landing": loc.get("landing_page_url") or "",
            "license": loc.get("license") or "",
            "method": "OpenAlex OA location",
        })
    return output


def unpaywall_pdf_candidates(client, doi):
    """Unpaywall's DOI endpoint is optional; a valid email is required.

    The Unpaywall title-search endpoint was retired in September 2026.
    """
    email = client.email
    if not email or "@" not in email or not doi:
        return []
    obj = client.request("https://api.unpaywall.org/v2/" + quote(doi, safe=""), {"email": email}) or {}
    if not obj.get("is_oa"):
        return []
    result, seen = [], set()
    for loc in [obj.get("best_oa_location"), *(obj.get("oa_locations") or [])]:
        if not isinstance(loc, dict):
            continue
        url = str(loc.get("url_for_pdf") or "").strip()
        if not url.lower().startswith("https://") or url in seen:
            continue
        seen.add(url)
        result.append({
            "url": url,
            "source": "Unpaywall: " + (loc.get("host_type") or "OA host"),
            "source_type": loc.get("host_type") or "unknown",
            "version": loc.get("version") or "",
            "landing": loc.get("url_for_landing_page") or "",
            "license": loc.get("license") or "",
            "method": "Unpaywall DOI lookup",
        })
    return result


def make_record(work, journal_field="", topic=""):
    source = (work.get("primary_location") or {}).get("source") or {}
    loc = best_oa(work)
    oa = work.get("open_access") or {}
    doi = normal_doi(work.get("doi"))
    authors = "; ".join(a.get("author", {}).get("display_name", "") for a in work.get("authorships", []) if a.get("author", {}).get("display_name"))
    record_id = doi or (work.get("id") or "").split("/")[-1]
    return {
        "record_id": record_id,
        "title": work.get("display_name") or work.get("title") or "",
        "authors": authors,
        "year": work.get("publication_year") or "",
        "publication_date": work.get("publication_date") or "",
        "journal": source.get("display_name") or "",
        "journal_field": journal_field,
        "doi": doi,
        "doi_url": "https://doi.org/" + doi if doi else "",
        "doi_verification": "not_checked",
        "publication_type": work.get("type") or "",
        "matched_topics": topic,
        "oa_status": oa.get("oa_status") or "",
        "is_oa": "yes" if loc else "no",
        "oa_license": loc.get("license") or "",
        "oa_version": loc.get("version") or "",
        "pdf_url": loc.get("pdf_url") or "",
        "oa_landing_url": loc.get("landing_page_url") or oa.get("oa_url") or "",
        "publisher_url": (work.get("primary_location") or {}).get("landing_page_url") or "",
        "openalex_id": work.get("id") or "",
        "cited_by_count": work.get("cited_by_count") or 0,
        "abstract": get_abstract(work.get("abstract_inverted_index")),
        "pdf_status": "not_attempted",
        "pdf_file": "",
        "verified_pdf_url": "",
        "pdf_link_status": "not_checked",
        "pdf_link_checked_at_utc": "",
        "pdf_source": "",
        "pdf_source_type": "",
        "pdf_version": "",
        "pdf_repository_landing_url": "",
        "pdf_candidates_checked": 0,
        "pdf_access_method": "",
        "_pdf_candidates": pdf_candidates_from_work(work),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def merge_record(existing, other):
    current = set(existing.get("matched_topics", "").split(" | ")) - {""}
    addition = set(other.get("matched_topics", "").split(" | ")) - {""}
    existing["matched_topics"] = " | ".join(sorted(current | addition))
    if existing.get("journal_field") == "" and other.get("journal_field"):
        existing["journal_field"] = other["journal_field"]
    known = {v["url"] for v in existing.get("_pdf_candidates", [])}
    existing.setdefault("_pdf_candidates", []).extend(v for v in other.get("_pdf_candidates", []) if v["url"] not in known)
    if existing.get("is_oa") != "yes" and other.get("is_oa") == "yes":
        for k in ("oa_status", "is_oa", "oa_license", "oa_version", "pdf_url", "oa_landing_url"):
            existing[k] = other[k]


def search_records(client, cfg, journals):
    records, log = {}, []
    for journal in journals:
        name = journal["journal"].strip()
        try:
            source = fetch_source(client, name)
        except Exception as e:
            print(f"[source error] {name}: {e}", file=sys.stderr)
            log.append({"journal": name, "topic": "", "status": "source_error", "count": 0, "detail": str(e)})
            continue
        if not source:
            print(f"[needs manual match] {name}", file=sys.stderr)
            log.append({"journal": name, "topic": "", "status": "source_not_exactly_matched", "count": 0, "detail": "Please check journal spelling / OpenAlex source"})
            continue
        source_id = source["id"].split("/")[-1]
        for topic in cfg["search_keywords"]:
            if len(records) >= cfg["max_total_records"]:
                break
            filt = f"primary_location.source.id:{source_id},from_publication_date:{cfg['year_from']}-01-01,to_publication_date:{cfg['year_to']}-12-31,type:article"
            limit = min(int(cfg["max_results_per_topic_journal"]), 100)
            try:
                data = client.request("https://api.openalex.org/works", {"search": topic, "filter": filt, "per_page": limit, "page": 1, "sort": "-relevance_score"}) or {}
                works = data.get("results", [])
                for work in works:
                    record = make_record(work, journal.get("field", ""), topic)
                    if not record["title"]:
                        continue
                    key = record["record_id"] or clean(record["title"])
                    if key in records:
                        merge_record(records[key], record)
                    elif len(records) < cfg["max_total_records"]:
                        records[key] = record
                log.append({"journal": name, "topic": topic, "status": "ok", "count": len(works), "detail": f"OpenAlex source {source_id}; first page; total matches {data.get('meta', {}).get('count', '?')}"})
                print(f"[search] {name}: {topic} -> {len(works)} records")
            except Exception as e:
                log.append({"journal": name, "topic": topic, "status": "error", "count": 0, "detail": str(e)})
                print(f"[search error] {name}: {topic}: {e}", file=sys.stderr)
        if len(records) >= cfg["max_total_records"]:
            break
    return list(records.values()), log


def read_doi_inputs(path):
    """Accept newline DOI TXT, RIS, or exported Scopus / WoS CSV / TSV.

    Importing a WoS/Scopus export does NOT call their subscription APIs.
    """
    path = Path(path)
    content = path.read_text(encoding="utf-8-sig")
    rows = []
    if path.suffix.lower() in (".csv", ".tsv"):
        import io
        # Excel/Scopus often exports UTF-8 CSV; WoS exports tab-separated files.
        dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
        try:
            dialect = csv.Sniffer().sniff(content[:4096], delimiters=",\t;")
        except csv.Error:
            pass
        reader = csv.DictReader(io.StringIO(content), dialect=dialect)
        columns = reader.fieldnames or []
        doi_column = next((c for c in columns if clean(c) in {"doi", "di", "digitalobjectidentifier", "doilink", "documentdoi"}), None)
        if not doi_column:
            raise ValueError("No DOI column in export. Accepts DOI, DI, Digital Object Identifier, DOI Link")
        rows = [str(row.get(doi_column) or "").strip() for row in reader]
    elif path.suffix.lower() == ".ris":
        rows = [m.group(1).strip() for line in content.splitlines() if (m := re.match(r"^DO\s*-\s*(.+)$", line, re.I))]
    else:
        rows = [line.strip() for line in content.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    valid = list(dict.fromkeys(d for line in rows if (d := normal_doi(line))))
    invalid = [line for line in rows if line and not normal_doi(line)]
    return valid, invalid


def doi_records(client, path):
    dois, invalids = read_doi_inputs(path)
    output, log = [], []
    for invalid in invalids:
        log.append({"journal": "DOI input", "topic": invalid[:150], "status": "invalid_doi", "count": 0, "detail": "Input not recognized as DOI"})
    for doi in dois:
        try:
            data = client.request("https://api.openalex.org/works", {"filter": "doi:" + doi, "per_page": 1}) or {}
            match = (data.get("results") or [None])[0]
            if match:
                output.append(make_record(match, topic="imported_DOI"))
                status = "matched"
            else:
                output.append({**{k: "" for k in FIELDS}, "record_id": doi, "doi": doi, "doi_url": "https://doi.org/" + doi, "matched_topics": "imported_DOI", "doi_verification": "not_checked", "pdf_status": "no_openalex_match", "_pdf_candidates": []})
                status = "not_found"
            log.append({"journal": "DOI input", "topic": doi, "status": status, "count": 1 if match else 0, "detail": "OpenAlex DOI lookup"})
        except Exception as e:
            log.append({"journal": "DOI input", "topic": doi, "status": "error", "count": 0, "detail": str(e)})
            print(f"[DOI error] {doi}: {e}", file=sys.stderr)
    return output, log


def verify_doi(client, record):
    doi = record.get("doi", "")
    if not doi:
        return "missing"
    try:
        obj = client.request("https://api.crossref.org/works/" + quote(doi, safe=""))
        if not obj:
            return "not_found_in_crossref"
        item = obj.get("message", {})
        other_title = (item.get("title") or [""])[0]
        our_title = record.get("title") or ""
        if not our_title:
            # Useful for DOI input even when no OpenAlex record is present.
            record["title"] = other_title
            record["journal"] = (item.get("container-title") or [""])[0]
            record["publication_type"] = item.get("type") or ""
            record["authors"] = "; ".join(" ".join((a.get("given", ""), a.get("family", ""))).strip() for a in item.get("author", []))
            date_parts = (item.get("published") or item.get("issued") or {}).get("date-parts") or []
            if date_parts and date_parts[0]:
                record["year"] = date_parts[0][0]
        if not our_title or not other_title:
            return "doi_found_title_unavailable"
        ratio = SequenceMatcher(None, clean(our_title), clean(other_title)).ratio()
        return "matched" if ratio >= .80 else "title_mismatch_check_manually"
    except Exception:
        return "verification_unavailable"


def safe_pdf_filename(rec):
    label = rec.get("doi") or rec.get("record_id") or clean(rec.get("title"))[:50]
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", label)[:135].strip("._")
    return (slug or "paper") + ".pdf"


def download_pdf(client, rec, folder, size_mb):
    # OpenAlex best_oa_location must mark the location OA. Only a direct PDF URL qualifies.
    if rec.get("is_oa") != "yes":
        return "not_open_access"
    url = rec.get("pdf_url") or ""
    if not url.lower().startswith("https://"):
        return "no_https_oa_pdf_link"
    # Do not guess a publisher's paywall bypass URL or send authorization cookies.
    try:
        data, final_url, content_type = client.request(url, binary=True, size_limit=int(float(size_mb) * 1024 * 1024))
        if not final_url.lower().startswith("https://"):
            return "non_https_redirect"
        if not data.startswith(b"%PDF-"):
            return "response_not_pdf"
        folder.mkdir(parents=True, exist_ok=True)
        filename = safe_pdf_filename(rec)
        target = folder / filename
        if target.exists():
            rec["pdf_file"] = str(Path("pdf") / filename)
            return "already_exists"
        target.write_bytes(data)
        rec["pdf_file"] = str(Path("pdf") / filename)
        return "downloaded"
    except (HTTPError, RuntimeError, URLError, OSError, ValueError) as e:
        return "download_failed: " + str(e)[:110]


def probe_pdf_link(client, url):
    """Anonymous GET-range probe; do not treat HTML, login or paywall as PDF.

    A successful probe confirms PDF signature bytes AT CHECK TIME,
    not guaranteed future availability or full-body integrity.
    """
    if not str(url).lower().startswith("https://"):
        return False, "", "insecure_or_non_https_link"
    delay = float(client.cfg.get("request_delay_seconds", .35))
    pause = delay - (time.monotonic() - client.last_request)
    if pause > 0:
        time.sleep(pause)
    client.last_request = time.monotonic()
    req = Request(url, headers={"User-Agent": client.ua, "Accept": "application/pdf,*/*", "Accept-Encoding": "identity", "Range": "bytes=0-4095"})
    try:
        with urlopen(req, timeout=float(client.cfg.get("request_timeout_seconds", 22))) as response:
            final = response.geturl()
            if not final.lower().startswith("https://"):
                return False, "", "redirected_to_non_https"
            sample = response.read(4096)
            ctype = response.headers.get("Content-Type", "").lower()
            if not sample.startswith(b"%PDF-"):
                return False, "", "returned_html_or_non_pdf" if "html" in ctype else "response_not_pdf"
            return True, final, "verified_pdf_header"
    except HTTPError as e:
        return False, "", "http_" + str(e.code)
    except (URLError, TimeoutError, OSError, ValueError) as e:
        return False, "", "probe_error: " + str(e)[:100]


def verify_free_pdf_links(client, record, cfg, download_enabled=False):
    """Verify all feasible locations until first anonymous downloadable PDF.

    Only successful probes can populate the strict final bibliography.
    If the actual download fails after probing, status still says a verified
    link existed at the time of inspection, not that file was downloaded.
    """
    candidates = list(record.get("_pdf_candidates") or [])
    errors = []
    checked = 0
    fallback_enabled = cfg.get("use_unpaywall_fallback", True)
    use_unpaywall = bool(client.email and "@" in client.email and fallback_enabled)
    attempted_fallback = False
    seen = {v["url"] for v in candidates}
    max_candidates = int(cfg.get("max_pdf_candidates_per_record", 15))
    while checked < max_candidates:
        if not candidates:
            if use_unpaywall and not attempted_fallback and record.get("doi"):
                attempted_fallback = True
                try:
                    new_candidates = unpaywall_pdf_candidates(client, record["doi"])
                    candidates.extend(v for v in new_candidates if v["url"] not in seen)
                except Exception as e:
                    errors.append("unpaywall_lookup_failed: " + str(e)[:80])
                if not candidates:
                    break
            else:
                break
        candidate = candidates.pop(0)
        checked += 1
        valid, final, status = probe_pdf_link(client, candidate["url"])
        if not valid:
            errors.append(candidate["source"] + ": " + status)
            continue
        record["verified_pdf_url"] = final
        record["pdf_url"] = final  # this field is verified in strict export
        record["pdf_link_status"] = "verified_pdf_header"
        record["pdf_link_checked_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record["pdf_source"] = candidate["source"]
        record["pdf_source_type"] = candidate["source_type"]
        record["pdf_version"] = candidate["version"]
        record["pdf_repository_landing_url"] = candidate["landing"]
        record["pdf_access_method"] = candidate["method"]
        record["pdf_candidates_checked"] = checked
        record["is_oa"] = "yes"
        record["oa_license"] = record.get("oa_license") or candidate.get("license") or ""
        if download_enabled:
            record["pdf_status"] = download_pdf(client, record, BASE / "pdf", cfg["max_pdf_size_mb"])
            if record["pdf_status"] in ("downloaded", "already_exists"):
                record["pdf_link_status"] = "downloaded_pdf_verified"
        else:
            record["pdf_status"] = "verified_link_not_saved"
        return True
    record["pdf_candidates_checked"] = checked
    record["pdf_link_status"] = "no_verified_free_pdf" if not errors else " | ".join(errors)[:380]
    record["pdf_status"] = "not_downloaded_no_verified_link"
    # A suggested or stale location is NOT a confirmed free download link.
    record["verified_pdf_url"] = ""
    return False


def quote_ris(s):
    return str(s or "").replace("\r", " ").replace("\n", " ")


def write_ris(records, path):
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write("TY  - JOUR\n")
            f.write("TI  - " + quote_ris(r.get("title")) + "\n")
            for a in (r.get("authors") or "").split("; "):
                if a:
                    f.write("AU  - " + quote_ris(a) + "\n")
            for tag, value in (("PY", r.get("year")), ("JO", r.get("journal")), ("DO", r.get("doi")), ("UR", r.get("doi_url") or r.get("oa_landing_url")), ("AB", r.get("abstract"))):
                if value:
                    f.write(f"{tag}  - {quote_ris(value)}\n")
            f.write("ER  - \n\n")


def write_bib(records, path):
    with path.open("w", encoding="utf-8") as f:
        for i, r in enumerate(records, 1):
            key = "eduref" + str(i)
            f.write(f"@article{{{key},\n")
            attrs = {"title": r.get("title"), "author": (r.get("authors") or "").replace("; ", " and "), "year": r.get("year"), "journal": r.get("journal"), "doi": r.get("doi"), "url": r.get("doi_url")}
            for field, value in attrs.items():
                if value:
                    safe_value = str(value).replace("\\", "\\textbackslash ").replace("{", "\\{").replace("}", "\\}").replace("\n", " ")
                    f.write(f"  {field} = {{{safe_value}}},\n")
            f.write("}\n\n")


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser(description="Find education journal literature and legal OA PDFs")
    p.add_argument("--mode", choices=["search", "doi"], default="search")
    p.add_argument("--input", default="input/seed_dois.txt", help="DOI file when --mode doi")
    p.add_argument("--check", action="store_true", help="Validate configuration, no network")
    p.add_argument("--no-pdf", action="store_true")
    p.add_argument("--no-verify", action="store_true")
    args = p.parse_args()
    cfg, journals = read_config()
    if args.check:
        print("CONFIG OK")
        print("Year range:", cfg["year_from"], "-", cfg["year_to"])
        print("Journals:", len(journals))
        print("Keywords:", " | ".join(cfg["search_keywords"]))
        print("API key present:", bool(os.environ.get("OPENALEX_API_KEY")))
        return
    client = HTTPClient(cfg)
    if args.mode == "search":
        records, log = search_records(client, cfg, journals)
    else:
        input_path = Path(args.input)
        if not input_path.is_absolute():
            input_path = BASE / input_path
        records, log = doi_records(client, input_path)
    if cfg.get("verify_doi_with_crossref") and not args.no_verify:
        print("[verify] Validating DOI metadata using Crossref")
        for rec in records:
            rec["doi_verification"] = verify_doi(client, rec)
    out = BASE / "output"
    out.mkdir(exist_ok=True)
    # Strict behavior: official bibliography contains ONLY verified direct PDF links.
    # Keep all records (including those failing the OA/PDF test) in separate audit CSV.
    strict = True
    verified, unverified = [], []
    downloads_used = 0
    allowed_downloads = int(cfg["max_pdf_downloads"]) if cfg.get("download_open_access_pdfs") and not args.no_pdf else 0
    for i, rec in enumerate(records, 1):
        may_download = downloads_used < allowed_downloads
        ok = verify_free_pdf_links(client, rec, cfg, download_enabled=may_download)
        if ok:
            verified.append(rec)
            if may_download:
                downloads_used += 1
            print(f"[verified PDF] {i}/{len(records)} {rec.get('title', '')[:52]} -> {rec.get('pdf_source', '')}")
        else:
            unverified.append(rec)
            print(f"[excluded no free PDF] {i}/{len(records)} {rec.get('title', '')[:52]}")
    public_records = verified
    write_csv(out / "all_results.csv", public_records, FIELDS)
    write_csv(out / "verified_free_pdf_results.csv", verified, FIELDS)
    write_csv(out / "open_access_results.csv", verified, FIELDS)
    write_csv(out / "search_candidates.csv", records, FIELDS)
    write_csv(out / "needs_manual_access.csv", unverified, FIELDS)
    write_csv(out / "search_log.csv", log, ["journal", "topic", "status", "count", "detail"])
    write_ris(verified, out / "references.ris")
    write_bib(verified, out / "references.bib")
    summary = {
        "mode": args.mode,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "strict_only_verified_free_pdf": strict,
        "search_queries": len([s for s in log if s["status"] == "ok"]),
        "candidate_records": len(records),
        "verified_free_pdf_links": len(verified),
        "excluded_no_verified_pdf_link": len(unverified),
        "actual_pdf_downloads": sum(r.get("pdf_status") == "downloaded" for r in records),
        "doi_verified_matches": sum(r.get("doi_verification") == "matched" for r in records),
        "errors": [s for s in log if s["status"] in ("error", "source_error", "source_not_exactly_matched", "invalid_doi")],
        "limits": {"max_results_per_topic_journal": cfg["max_results_per_topic_journal"], "max_total_records": cfg["max_total_records"], "max_pdf_candidates_per_record": cfg.get("max_pdf_candidates_per_record", 15)},
        "notes": "Verified = anonymous HTTPS GET served bytes beginning %PDF- at retrieval time. Link may later expire, be redirected, or provide a manuscript rather than publisher version. Scopus/WoS imports are metadata, not direct database API coverage. Search is not exhaustive; top-journal list is not a verified JCR ranking."
    }
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nDONE: candidates", len(records), "| VERIFIED FREE PDF LINKS", len(verified), "| actual downloads", summary["actual_pdf_downloads"])
    print("Main results (strict):", out / "verified_free_pdf_results.csv")
    print("Non-qualified candidates:", out / "needs_manual_access.csv")
    if not verified:
        print("No verified PDF links. Inspect search_candidates.csv and search_log.csv; ensure OA-host domains are allowed and email set for optional Unpaywall. Do NOT claim that articles with only OA landing pages meet the free-download requirement.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)
