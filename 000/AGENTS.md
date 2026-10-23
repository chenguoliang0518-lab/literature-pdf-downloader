# Codex instructions — Education top-journal literature + strictly verified FREE PDF links (v2)

## Invariant: NO VERIFIED PDF LINK, NO FORMAL RESULT

User's strict requirement: The final result can include a journal article ONLY when `verified_pdf_url` is an anonymized-accessible HTTPS direct download that has successfully been HTTP-tested as actual `%PDF-` content (anonymous Range GET).

- Exclude articles with just DOI, indexed abstract, OA flag, landing page, gated institutional subscription, publisher access button or untested guessed link.
- Even if Scopus/WoS labels an article OA, do not treat it as an actually downloaded PDF without verification.
- The positive formal list is `output/verified_free_pdf_results.csv`, **not** `search_candidates.csv`.
- `output/all_results.csv`, `output/open_access_results.csv`, `references.ris` and `references.bib` must contain only passed articles under `require_verified_free_pdf=true`.
- If no article has a verified free PDF, report ZERO positive records, not an invented dataset. Other articles may appear ONLY in `search_candidates.csv` and `needs_manual_access.csv` as excluded audit candidates.
- Keep timestamps and source names for every verified link; distinguish a verified PDF **URL** from a successfully saved PDF **file**.

## Operation

1. Read `README_中文.md`, `config/settings.json`, `config/journals.csv` and run `python run.py --check` plus `python -m unittest discover -s tests -v`.
2. Respect the user's actual topic/years/journal subset. Defaults are examples, not the user's confirmed project. Do not silently broaden or replace search terms.
3. For journal/topic searches: `python run.py --mode search --no-pdf` initially validates direct free PDF links without saving PDF files. Then `python run.py --mode search` also saves some PDFs if host domains allow. The no-pdf mode is NOT metadata-only; its link validation still uses anonymous GETs.
4. Import user-exported Scopus/WoS `.csv`, `.tsv`, or `.ris` using `python run.py --mode doi --input input/<filename>`; alternatively `.txt` with one DOI/line. This is **not a direct Scopus/WoS API query**.
5. OpenAlex supplies metadata and all known OA host copies including university repositories. Optional `SCHOLAR_EMAIL` permits Unpaywall DOI supplementary lookup. Use Crossref for DOI checks. The program does not directly query ERIC, Scopus or WoS APIs.
6. Review `output/search_log.csv` for source matching/errors. Do not claim completeness, current JCR ranking, or actual downloads not shown in output.
7. In Codex Cloud, only request internet allowed domains from user/environment controls: OpenAlex, Crossref, optional Unpaywall, and HTTPS PDF hosts as discovered. When hosts are blocked, classify as unverified, never as successful.
8. If a PDF candidate has only a public landing page, you may suggest a manual follow-up on the university repository, ERIC or publisher pages, but do not fabricate a direct PDF URL. If supplementing candidates by browsing, actually test the URL before including them in formal results and include traceable evidence/source/time.

## Strict access safety

Never bypass CAPTCHA, login, paywalls, library proxies, rate limits, robots restrictions, institution credentials or cookies; no Sci-Hub or unauthorized mirrors. Never post personal secrets, API keys, institutional credentials or full articles to GitHub. University repository author-accepted manuscripts may differ from the version of record: record version and license when available. Use moderate rate limits.

## Deliverables

- Main: `output/verified_free_pdf_results.csv` with required verified `verified_pdf_url`.
- Audit: `output/search_candidates.csv`, `output/needs_manual_access.csv`.
- `output/references.ris`, `output/references.bib`, `output/run_summary.json`, `output/search_log.csv`.
- Optional local downloads: `pdf/*.pdf` (Git-ignored). Codex Cloud does not automatically synchronize its downloaded files to Windows.

Summary must report searched sources vs imported databases, number of candidate articles, number of **verified direct free PDF links**, number of actual downloaded files, DOI check statuses, main excluded causes, and limitations. If user asks only for articles with free download links, do NOT display excluded audit candidates as recommendations.
