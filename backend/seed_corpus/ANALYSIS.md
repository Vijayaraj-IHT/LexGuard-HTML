# Lexguard Seed Corpus — Analysis Report

**Source:** [Google Drive folder `1SUvTnpN6EbhO9nDR_EVJPMjNt5dJHZGu`](https://drive.google.com/drive/folders/1SUvTnpN6EbhO9nDR_EVJPMjNt5dJHZGu)
**Corpus size:** 29 PDFs · 7,629,514 bytes (≈ 7.3 MiB) · all verified as valid `%PDF` files
**Acquired:** 2026-10-12 · byte sizes verified identical to Drive metadata · SHA-256 computed for every file (see `manifest.json`)

---

## 1. What the corpus is

The folder is a snapshot of **judgments and orders of Indian High Courts**, almost all pronounced in the **first week of October 2026** (bulk download from the Madras High Court's JUDIS portal, `mhc.tn.gov.in/judis`), plus a few older pending matters decided the same year from other High Courts.

Two naming generations exist in Drive:

| Naming pattern | Count | Origin |
|---|---|---|
| `Home \| Judgements and Orders, Supreme Court and High courts of India.pdf` | 6 | Browser "save as PDF" of JUDIS pages — **generic page title, all identical**, so they collide on disk (downloaded sequentially and renamed here) |
| Content-hash style names (e.g. `59cfbf77…765.pdf`) | 23 | Hash-named exports, likely from a bulk harvester/scraper of JUDIS |
| *(no folder structure / subfolders)* | — | Flat folder, no categorisation |

All 29 PDFs have been downloaded into `backend/seed_corpus/pdfs/` with **deduplicated, case-number-based filenames** (`NN_<case-no>.pdf`) and registered in `manifest.json`.

---

## 2. Court distribution

| Court | PDFs | Share |
|---|---:|---:|
| Madras High Court (Principal Seat, Chennai) | 15 | 51.7% |
| Madras High Court (Madurai Bench) | 10 | 34.5% |
| High Court of Chhattisgarh at Bilaspur | 2 | 6.9% |
| High Court of Judicature at Patna | 1 | 3.4% |
| High Court of Punjab and Haryana at Chandigarh | 1 | 3.4% |
| **Total** | **29** | 100% |

> **25 of 29 (86.2%) are Madras High Court documents** — an excellent fit for a single-jurisdiction demo corpus, with three other High Courts providing diversity for multi-court search tests.

---

## 3. Subject-matter (case type) distribution

| Case type | PDFs |
|---|---:|
| Criminal — Bail / bail conditions | 8 |
| Criminal — Quashing, sentence suspension | 4 |
| Contempt of Court | 3 |
| Writ — Criminal (police protection, prison leave) | 3 |
| Service / Recruitment / Gratuity (Art. 226) | 5 |
| Civil — Commercial (trademark/passing off) | 2 |
| Civil — Family, Testamentary, Motor Accident, Limitation | 4 |
| Writ — Education (MBBS admissions) | 1 |

**Thematic keyword clusters** (from `keyword_tags` in the manifest):

1. **Bail jurisprudence** — NDPS (4 matters, ganja seizures of 62–100 kg), Arms Act, BNS murder cases, SC/ST (PoA) appeals.
2. **Contempt of court** — compliance, maintainability, abeyance (all three closed on 09.10.2026).
3. **Service law** — notional promotions & arrears, gratuity denial, PH-quota recruitment, BPSC disputes.
4. **Intellectual property** — `ANNAPOORNA vs ANNAPURNA` and `TRUE VALLEY vs AMUL TRU` (both before Justice A.D. Maria Clete).
5. **Public order / events** — police protection for festivals and tournaments.

---

## 4. Statutes & legal framework referenced

| Statute / code | Mentions (approx.) |
|---|---:|
| **Bharatiya Nyaya Sanhita, 2023 (BNS)** | 6 |
| **Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)** | 7 |
| **NDPS Act, 1985** | 4 |
| Constitution of India (Article 226) | 9 |
| Contempt of Courts Act, 1971 | 3 |
| Trade Marks Act, 1999 | 2 |
| IPC / CrPC (legacy, pre-2024 cases) | 3 |
| Arms Act 1959 · MV Act 1988 · SC/ST (PoA) Act 1989 · Indian Succession Act · TNPHW Act 2022 | 1 each |

**Note for the project:** this corpus exercises *both* the new criminal codes (BNS/BNSS) **and** legacy IPC/CrPC — ideal for testing the NER/`section_tags` extraction and precedent search over statute names.

---

## 5. Temporal profile

| Decision date | Count |
|---|---:|
| **09.10.2026** (Madras HC — single-day batch) | 25 |
| 15.06.2026 (Chhattisgarh) | 1 |
| 23.06.2026 (Patna) | 1 |
| 17.08.2026 (P&H) | 1 |
| 18.08.2026 (Chhattisgarh) | 1 |

Filing/case years span **2015 → 2026** (T.O.S. 12/2015 is the oldest matter; most are 2022–2026 filings).

---

## 6. Data-quality findings ⚠️

1. **Duplicate filenames in Drive** — the 6 `Home | …pdf` files are *different judgments* under one name; naive downloading overwrites 5 of them. Our acquisition sequence handled this.
2. **Hash filenames carry no metadata** — case numbers/courts only recoverable by reading content (done for all 29; see manifest).
3. **`20_cma-md-856-2019.pdf` caption mismatch** — header says `CMA(MD) No. 856 of 2019`, body references `CMA(MD) No. 104 of 2024` (CNR `HCMD011231132023`). Possibly a mis-indexed JUDIS export; flagged in the manifest summary.
4. **`28_cwp-1744-2024-ph.pdf` is text-layer noisy** — the P&H judgment PDF (963 KB) contains repeated/duplicated OCR-style text blocks; good stress test for text extraction & embedding quality.
5. **No Supreme Court documents** despite the Drive folder name — corpus is High-Court only.
6. **Missing judges** on `26_wps-5957-2023-cg.pdf` (not stated in the first pages of the extraction) — manifest leaves `judge: null`.

---

## 7. How the corpus maps to Lexguard features

| Lexguard feature | Seed-corpus usage |
|---|---|
| **SHA-256 ingestion & duplicate detection** (`crypto_service`) | 29 pre-computed hashes in `manifest.json`; re-upload must raise `409 Conflict` |
| **Tamper-evident audit chain** | Uploading all 29 exercises the hash-chained ledger at volume |
| **Approval workflow (RBAC)** | Script can upload as `court_staff` and approve as `senior_staff` |
| **NER / auto-tagging** (`ner_service`) | Manifest `act_tags`/`section_tags` act as ground truth vs. auto-extraction |
| **Semantic precedent search** (InLegalBERT / MiniLM) | Ready-made demo queries: *"bail in NDPS cases with 100 kg ganja"*, *"notional promotion arrears"*, *"trademark passing off AMUL"*, *"contempt for non-compliance"* |
| **Draft Assistant gap analysis** | Petition drafts can cite verified corpus cases (e.g. CRL OP 26220/2026 for NDPS bail factors) |

---

## 8. Recommended next steps

1. **Seed the platform:** `python backend/seed_corpus/seed_corpus.py` (see `README.md` in this directory).
2. **Verify integrity:** compare recomputed hashes against `manifest.json` (the exact flow the `/cases/{id}/verify` endpoint performs).
3. **Index embeddings** on ingest, then run the five demo queries above as search acceptance tests.
4. **Expand diversity** — request additional folders covering Supreme Court and district court orders to reduce the 90% Madras-HC skew.
