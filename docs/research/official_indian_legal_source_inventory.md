# Official Indian Legal Source Inventory and Acquisition Feasibility Report

## 1. Executive Summary

This report establishes the first comprehensive, machine-readable official legal source inventory for CaseSeva's Indian law architecture. It details the operational, technical, and legal characteristics of official portals across:
1. Central Legislation
2. Ministry / Department Portals
3. Judiciary (Supreme Court, High Courts, eCourts)
4. State Legislation & Gazettes
5. Tribunals & Regulatory Authorities

### Critical Architectural Principle: Discovery vs. Trust
Under CaseSeva's Phase 4 invariants:
$$\text{DISCOVERED / DOWNLOADED} \neq \text{REVIEWED / CURRENT LAW}$$
No automated crawler, parser, scraping pipeline, or inference model can promote any legal text into the active verified corpus. All automated pipelines terminate at `REVIEW_PENDING`, requiring explicit, independent administrative review via `AuthorityReview.decide()` before any provision is eligible for citation or statutory grounding.

---

## 2. Official Source Inventory Matrix

| Source Name | Official Domain | Owner / Ministry | Category | Content Types | Feasibility | API / Feed | HTML Index | PDFs / Download | CAPTCHA / Access Restrictions | Recommended Acquisition Method | Priority | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **India Code Portal** | `indiacode.gov.in` | Legislative Dept, Ministry of Law & Justice | Central Legislation | Acts, Amendment Acts, Rules, Regulations, Orders, Notifications | High | DSpace REST API (`backend.indiacode.gov.in`) | Yes | Yes (PDF & HTML) | None; Rate limits observed (`X-RateLimit-Limit: 500`) | `STABLE_HTTP_INDEX` | P0 | AUTOMATABLE_VALIDATED |
| **India Code Legacy** | `www.indiacode.nic.in` | Legislative Dept, Ministry of Law & Justice | Central Legislation | Migration notice | N/A | None | Redirect | Meta-refresh | Redirects to `indiacode.gov.in` | Deprecated (Track redirect) | P3 | MIGRATED |
| **Legislative Department** | `legislative.gov.in` | Ministry of Law and Justice | Central Legislation | Constitution, Annual Acts, Ordinances, Bills | High | None | Yes | Yes (PDF) | None; Standard NIC Drupal CMS | `DETERMINISTIC_HTML` | P0 | AUTOMATABLE_VALIDATED |
| **The Gazette of India (eGazette)** | `egazette.gov.in` | Directorate of Printing, MoHUA | Central Legislation | Notifications, Statutory Orders, Extraordinary Gazettes | Low (Automated) | None | Session-based ASPX | Yes (PDF) | Session tokens & mathematical CAPTCHA on search | `MANUAL_OR_BROWSER_REVIEW_REQUIRED` | P0 | MANUAL_BROWSER_ONLY |
| **Dept of Consumer Affairs** | `consumeraffairs.nic.in` | Ministry of Consumer Affairs, Food & PD | Ministry / Dept | Rules, Regulations, Notifications, Guidelines | Medium | None | Yes | Yes (PDF) | Intermittent SSL handshake delays; No CAPTCHA | `DETERMINISTIC_HTML` | P1 | AUTOMATABLE_VALIDATED |
| **MeitY** | `meity.gov.in` | Ministry of Electronics & IT | Ministry / Dept | Rules, Guidelines, Orders, Notifications | High | None | Yes | Yes (PDF) | None; Standard NIC Drupal CMS | `DETERMINISTIC_HTML` | P1 | AUTOMATABLE_VALIDATED |
| **Ministry of Labour & Employment** | `labour.gov.in` | Ministry of Labour & Employment | Ministry / Dept | Labour Codes, Rules, Circulars | High | None | Yes | Yes (PDF) | None; Standard NIC CMS | `DETERMINISTIC_HTML` | P1 | AUTOMATABLE_VALIDATED |
| **Supreme Court of India (e-SCR)** | `sci.gov.in` / `escr.sci.gov.in` | Supreme Court of India | Judiciary | Judgments, Daily Orders, Precedents | Medium | e-SCR portal | Yes | Yes (PDF) | Occasional rate throttling; Bot detection during peak hours | `MANUAL_OR_BROWSER_REVIEW_REQUIRED` | P0 | MANUAL_BROWSER_ONLY |
| **eCourts National Portal** | `judgments.ecourts.gov.in` | e-Committee, Supreme Court & Dept of Justice | Judiciary | Judgments, Final Orders | Low (Automated) | None | Yes | Yes (PDF) | Mandatory image CAPTCHA on search form | `MANUAL_OR_BROWSER_REVIEW_REQUIRED` | P1 | MANUAL_BROWSER_ONLY |
| **Madras High Court** | `hcmadras.tn.gov.in` | High Court of Judicature at Madras | Judiciary | High Court Judgments, Notifications | Low (Automated) | None | Yes | Yes (PDF) | CAPTCHA verification on judgment search | `MANUAL_OR_BROWSER_REVIEW_REQUIRED` | P1 | MANUAL_BROWSER_ONLY |
| **Tamil Nadu Government Gazette** | `stationeryprinting.tn.gov.in` | Dept of Stationery & Printing, Govt of Tamil Nadu | State Legislation | State Acts, Rules, Notifications | High | None | Yes (Chronological) | Yes (PDF) | None; Standard Nginx web server | `DETERMINISTIC_HTML` | P2 | AUTOMATABLE_VALIDATED |
| **NCDRC Portal** | `ncdrc.nic.in` | National Consumer Disputes Redressal Commission | Tribunal / Regulator | Orders, Regulations, Causelists | High | None | Yes | Yes (HTML & PDF) | None on causelists and orders | `DETERMINISTIC_HTML` | P1 | AUTOMATABLE_VALIDATED |
| **Competition Commission (CCI)** | `cci.gov.in` | Ministry of Corporate Affairs | Tribunal / Regulator | Orders, Regulations, Merger Approvals | High | None | Yes | Yes (PDF) | None; Categorized public CMS | `DETERMINISTIC_HTML` | P2 | AUTOMATABLE_VALIDATED |

---

## 3. Empirical Live Discovery Probe Findings

Live, read-only discovery probes executed against official endpoints yielded critical empirical insights:

1. **India Code Infrastructure Migration**:
   - `https://www.indiacode.nic.in/` returned HTTP 200 with `<meta http-equiv="refresh" content="3;url=https://indiacode.gov.in">`, confirming migration to the national portal domain `indiacode.gov.in`.
   - `https://indiacode.gov.in/` is active and responsive (296 ms latency).
   - Probing revealed active rate limiting headers: `X-RateLimit-Limit: 500`, `X-RateLimit-Remaining: 499`. Ingestion adapters MUST implement backoff and respect rate headers.
   - Page source revealed underlying DSpace 7 architecture communicating with `https://backend.indiacode.gov.in`.

2. **eGazette ASPX Session Architecture**:
   - `https://egazette.gov.in/` redirected to a sessionized URL: `https://egazette.gov.in/(S(oquuxkfnj3d3lnpkzt0eqqhm))/default.aspx`.
   - Search forms implement mathematical image CAPTCHAs. Automated bypass is strictly prohibited. The system mandates `MANUAL_OR_BROWSER_REVIEW_REQUIRED`.

3. **Judicial Portal CAPTCHA Protection**:
   - `judgments.ecourts.gov.in` redirected to `/pdfsearch/index.php`. The judgment search form requires image CAPTCHA input for every query.
   - Bulk judgment retrieval cannot be automated ethically. CaseSeva implements targeted, advocate-driven browser acquisition rather than mass-scraping.

4. **Network Resilience & NIC Gateway Timeouts**:
   - `https://consumeraffairs.nic.in/` experienced an SSL handshake timeout after 12.5 seconds during probing, reflecting known intermittent gateway congestion on Central NIC servers. Adapters must employ exponential retry with jitter.

---

## 4. Ingestion Prework Architecture

All prework source code is completely isolated in `engineering_prework/legal_source_ingestion/`:

1. **`models.py`**:
   - `AuthorityType`: Comprehensive legal authority enumeration covering Constitution provisions, Acts, Amendment Acts, Rules, Regulations, Notifications, Orders, Ordinances, Circulars, Guidelines, Judgments, and Precedents.
   - `ProvisionRecord`: Granular provision entity capturing Part, Chapter, Section, Subsection, Clause, Subclause, Proviso, and Explanation with exact substring boundaries (`section_start`, `section_end`), raw document hash, and extracted text hash.
   - `VersionRelationship`: Immutable version graph relationship (`AMENDED_BY`, `CORRECTED_BY`, `COMMENCED_BY`, `SUPPLEMENTED_BY`, `INTERPRETED_BY`).
   - `JudgmentRecord`: Structured judicial entity with court, bench, case number, decision date, parties, neutral citations, cited statutes, disposition, and hierarchy ranking.

2. **`sectionizer.py`**:
   - `StatutorySectionizer`: Hierarchical parser for Indian statutory formatting (`1. Short title...`, `(1)`, `(2)`, `(a)`, `(b)`). Guarantees `extracted.text_content[start:end] == quote`.

3. **`version_graph.py`**:
   - `VersionGraph`: Evaluates temporal in-force validity based on verified commencement notifications and repeals, returning `IN_FORCE`, `PRE_COMMENCEMENT`, or `REPEALED`.

4. **`base_adapter.py`**:
   - `BaseSourceAdapter`: Defines clean abstract lifecycle: `discover_documents`, `fetch_document`, `extract_metadata`, `extract_text`, `enumerate_sections`, `detect_version_metadata`, `discover_related_amendments`, `build_provenance`.

5. **`adapters/`**:
   - `IndiaCodeAdapter`: DSpace handle handling, statutory sectionization, amendment link extraction.
   - `MinistryPortalAdapter`: Subordinate rules, notifications, and regulations.
   - `JudgmentSourceAdapter`: Structured judicial records with citation indexes and disposition.
