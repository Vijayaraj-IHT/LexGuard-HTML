# Case-file pattern analysis

Generated: `2026-10-31T20:42:38.952823Z`

- Directories scanned: `backend/seed_corpus/pdfs`, `backend/incoming_cases`
- PDFs scanned: **79** · unique documents: **52** · duplicates skipped: 27 · failures: 0

## 1. Detected drafting profiles

| Profile | Documents | Mean key coverage | Mean facts length | Pages | Example |
|---|---:|---:|---:|---|---|
| `MHC-MB-CORAM-ORDER` — Madras HC, Madurai Bench — CORAM + DATED order | 17 | 0.47 | 2503 | 4–22 | `14ivgIcoWlB9bxfVBmDphUqU0lwY8e4ox_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` |
| `MHC-PS-CORAM-ORDER` — Madras HC, Principal Seat — CORAM + DATED order | 11 | 0.46 | 2610 | 2–11 | `11LXarK_RnsKcXY4VMl02kRlH_73qSKma_HCMA012449822026.pdf` |
| `MHC-MB-RESERVED-JUDGMENT` — Madras HC, Madurai Bench — reserved long-form judgment | 8 | 0.48 | 4113 | 6–46 | `1486lPB_2WXf96eigWnEquO46JCZFgrTy_HCMD011029782023.pdf` |
| `MHC-MB-CRIM-JURIS` — Madras HC, Madurai Bench — 'Criminal Jurisdiction' order sheet | 8 | 0.51 | 3179 | 5–30 | `14KoOLo5lvWR98wLvh_PuaC3vo4y4Nop9_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` |
| `MHC-PS-RESERVED-JUDGMENT` — Madras HC, Principal Seat — reserved long-form judgment | 4 | 0.52 | 3556 | 16–32 | `11ni-CfeN3epU9ANxIO0D2fGDYC_0j5jy_a2589f04972a77de9b4f22192bdbc9ccbe5c603b7d06c31c06a80bbbceaf15d61791784333.pdf` |
| `CGHC-BILASPUR-ORDER` — Chhattisgarh HC at Bilaspur — AFR/NAFR order on board | 2 | 0.66 | 3715 | 3–56 | `1OiqoDsDL8pFHOY-guAb6LJ5w1-yZUa9R_CGHC010231782022.pdf` |
| `PATNA-CWJC-JUDGMENT` — Patna HC — Civil Writ Jurisdiction Case judgment | 1 | 0.70 | 4457 | 38–38 | `1RlQQrZbRqiU7EcTrYkPcIwQFL88mxGpH_7cc2e81521982c03012b04a4a04da78a0de74f008fba78e217496d3b6a55b79c1791784284.pdf` |
| `PHHC-CWP-COLUMNAR` — Punjab & Haryana HC — CWP (O&M) columnar judgment | 1 | 0.60 | 4411 | 14–14 | `28_cwp-1744-2024-ph.pdf` |

## 2. Facts-extraction strategy used

| Strategy | Documents |
|---|---:|
| `anchored_span` | 31 |
| `paragraph_scan` | 19 |
| `post_caption_body` | 1 |
| `explicit_heading` | 1 |

## 3. Layout signals

| Signal | Documents | Meaning |
|---|---:|---|
| `layout:watermark` | 44 | Repeating JUDIS/registry watermark |
| `layout:serif` | 43 | Times / serif dominant (judgment typesetting) |
| `layout:a4_page` | 43 | A4 page (≈595x842) — JUDIS / MHC |
| `layout:legal_page` | 4 | Legal-size page (>= 600x950 pt) — CGHC / Patna / P&H |
| `layout:mono_font` | 3 | Courier / monospace dominant (Madurai criminal template) |
| `layout:clipped_blocks` | 1 | Text drawn as clipped/overlapping blocks — needs geometric repair |
| `layout:columnar` | 1 | Genuine multi-column blocks present |

## 4. Text-layer quality

| Quality | Documents |
|---|---:|
| `good` | 51 |
| `repaired` | 1 |

## 5. Key sets — which anchors fire

Declared keys per category:

| Category | Keys declared | Hit documents |
|---|---:|---:|
| `coram` | 68 | 41 |
| `counsel` | 104 | 97 |
| `dates` | 150 | 70 |
| `facts` | 107 | 70 |
| `forum` | 115 | 65 |
| `identity` | 121 | 69 |
| `issues` | 52 | 7 |
| `noise` | 319 | 12 |
| `operative` | 52 | 17 |
| `parties` | 164 | 139 |
| `reasoning` | 52 | 23 |
| `relief` | 52 | 49 |
| `signature` | 65 | 50 |
| `statute_style` | 99 | 48 |

Top individual keys (documents in which the anchor matched):

| Key | Documents |
|---|---:|
| `parties.versus` | 51 |
| `dates.decision_date` | 50 |
| `relief.prayer` | 49 |
| `counsel.for_petitioner` | 48 |
| `counsel.for_respondent` | 47 |
| `signature.judge_sign` | 45 |
| `forum.court_line` | 44 |
| `parties.respondent` | 43 |
| `facts.start` | 43 |
| `parties.petitioner` | 42 |
| `identity.case_no` | 40 |
| `statute_style.sections` | 35 |
| `coram.judge` | 27 |
| `facts.end` | 26 |
| `reasoning.from` | 23 |
| `identity.cnr` | 22 |
| `operative.conclusion` | 17 |
| `dates.reserved_on` | 11 |
| `coram.signature_name` | 11 |
| `dates.pronounced_on` | 9 |
| `forum.bench` | 9 |
| `forum.jurisdiction` | 8 |
| `issues.issues` | 7 |
| `noise.bare_page_number` | 6 |
| `statute_style.read_with` | 5 |
| `signature.pre_delivery_order` | 4 |
| `statute_style.articles` | 3 |
| `statute_style.bail_provision` | 3 |
| `noise.cav_marker` | 3 |
| `parties.accused_tag` | 3 |

## 6. Per-document results

| File | Profile | Conf. | Keys | Facts | Layout |
|---|---|---:|---|---:|---|
| `11LXarK_RnsKcXY4VMl02kRlH_73qSKma_HCMA012449822026.pdf` | `MHC-PS-CORAM-ORDER` | 0.84 | 11/30 | 1729 | serif, a4_page, watermark |
| `11ni-CfeN3epU9ANxIO0D2fGDYC_0j5jy_a2589f04972a77de9b4f22192bdbc9ccbe5c603b7d06c31c06a80bbbceaf15d61791784333.pdf` | `MHC-PS-RESERVED-JUDGMENT` | 0.93 | 13/31 | 3016 | serif, a4_page, watermark |
| `13UQY8c3-igXrEEGZff-qQk9B9Fyh1jId_HCMA012161402026.pdf` | `MHC-PS-CORAM-ORDER` | 0.88 | 17/30 | 4460 | serif, a4_page, watermark |
| `140C0Zd_RuyRJ1__1eVvrSYvUKw7rwkQU_3aba42b3cf2b11ec95900b9d85a75aed78e84ad282c9cb2f24ad242cfe04fcc21791784734.pdf` | `MHC-PS-RESERVED-JUDGMENT` | 0.93 | 17/31 | 2666 | serif, a4_page, watermark |
| `1486lPB_2WXf96eigWnEquO46JCZFgrTy_HCMD011029782023.pdf` | `MHC-MB-RESERVED-JUDGMENT` | 1.00 | 14/31 | 4385 | serif, a4_page, watermark |
| `14KoOLo5lvWR98wLvh_PuaC3vo4y4Nop9_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CRIM-JURIS` | 0.90 | 11/29 | 4351 | serif, a4_page, watermark |
| `14ivgIcoWlB9bxfVBmDphUqU0lwY8e4ox_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.85 | 10/27 | 3981 | serif, a4_page, watermark |
| `15G50-aNurToRwuEmMqRDpbirnRNYMDRN_HCMD011922102025.pdf` | `MHC-MB-RESERVED-JUDGMENT` | 1.00 | 17/31 | 4496 | serif, a4_page, watermark |
| `16g98aEbA6BgNKNd-y8X5Gl1kQRVzXNZO_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-RESERVED-JUDGMENT` | 1.00 | 10/31 | 4413 | serif, a4_page, watermark |
| `17AGNXj_YQrgvBUHnU2C9QLNrlqQ9e2Pe_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.85 | 12/27 | 1652 | serif, a4_page, watermark |
| `1AA_my9aHYi-R_0M-My9DzzKBNkdn_j3E_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.88 | 17/27 | 4406 | serif, a4_page, watermark |
| `1BH4RAfpoh0YQAKaLwRsmLK5e387b_Jmx_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CRIM-JURIS` | 0.90 | 14/29 | 4373 | serif, a4_page, watermark |
| `1DsZk4h2aBlJp1NTrNWXENYM3cGdbr0XA_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.88 | 15/27 | 3347 | serif, a4_page, watermark |
| `1DwxnUosNBio6lsh_TMyN0N9n9nHFI52E_HCMA012247452026.pdf` | `MHC-PS-CORAM-ORDER` | 0.88 | 15/30 | 2226 | serif, a4_page, watermark |
| `1EubyoDaLKuT5eObjocQck-9PQsZLL5o__Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.85 | 12/27 | 1205 | serif, a4_page, watermark |
| `1GGJ3zxC_2p9i9iZQ7VnlJpc1Jxg6IEFE_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CRIM-JURIS` | 0.90 | 13/29 | 2953 | serif |
| `1GHG2DhwwK7UIq5Ucw0xc_Fg4gMed5ryd_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-RESERVED-JUDGMENT` | 0.93 | 17/31 | 3918 | serif, a4_page, watermark |
| `1H3kNP6p05g_lGPyp1z5bMlQxfjrf4Ic0_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.85 | 12/27 | 2635 | serif, a4_page, watermark |
| `1HzxSYCj_cqv9peYTvyk42HpMofLyREjV_HCMA012140432026.pdf` | `MHC-PS-CORAM-ORDER` | 0.88 | 17/30 | 4412 | serif, a4_page, watermark |
| `1JwCCfpruUm0P4Roe2qex2Fdj8SFTWQBn_CRL_OP_MD_23054_2026.pdf` | `MHC-MB-CRIM-JURIS` | 0.82 | 14/29 | 864 | serif, a4_page, watermark |
| `1NNSVgANn4M4BzaHEVlprgDaBKOkGaypv_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.85 | 12/27 | 1454 | serif, a4_page, watermark |
| `1NNsJucUQ1J6EsUBcdTCgEaEX3SA51731_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.83 | 10/27 | 1815 | serif, a4_page, watermark |
| `1ORsOgidZuMWola8LKnpLeYAJLsfHj350_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-RESERVED-JUDGMENT` | 1.00 | 14/31 | 4369 | serif, a4_page, watermark |
| `1OiqoDsDL8pFHOY-guAb6LJ5w1-yZUa9R_CGHC010231782022.pdf` | `CGHC-BILASPUR-ORDER` | 0.76 | 21/32 | 3134 | legal_page |
| `1Plk5VWP7PUpnIGQcOnckgtksmJ-7VGp1_HCMD011427832026.pdf` | `MHC-MB-CORAM-ORDER` | 0.88 | 13/27 | 3659 | serif, a4_page, watermark |
| `1RlQQrZbRqiU7EcTrYkPcIwQFL88mxGpH_7cc2e81521982c03012b04a4a04da78a0de74f008fba78e217496d3b6a55b79c1791784284.pdf` | `PATNA-CWJC-JUDGMENT` | 0.95 | 23/33 | 4457 | serif, legal_page |
| `1SjmcJXmOO5jRB_9EyS-2PJmsCS5C1Scm_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-RESERVED-JUDGMENT` | 1.00 | 17/31 | 3542 | serif, a4_page, watermark |
| `1TyMlNjSW3YklQWmQJpw3Gnh0vy87sibS_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CRIM-JURIS` | 0.77 | 20/29 | 4406 | mono_font |
| `1U_B1zgRMLt89dMviyNJx2HHLRe6---oy_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-RESERVED-JUDGMENT` | 1.00 | 12/31 | 4287 | serif, a4_page, watermark |
| `1WEi-N1P3eTNeFayRGdiekbPVSaLPsl_b_bf2dca4db3b8f8eaeec433ef599b448c760027e87f9408c88feb56980930f0631791784749.pdf` | `MHC-MB-CRIM-JURIS` | 1.00 | 16/29 | 3541 | mono_font |
| `1WJfTK7jLXJGqBzAkKp8Xd7-ppRHar3Mp_6ba43cfe612f7db26bfb16043127fa9a5d4842a2bd511276b716c97cd254a1b11791784291.pdf` | `CGHC-BILASPUR-ORDER` | 1.00 | 21/32 | 4296 | legal_page |
| `1ZAcX7ltM8tvYsgIreNdTmrC2FxHLtT8__626f12e08ea94387433d8798f04cc70af6068f3c4ba79bfd9bc2ae70ef27244e1791784494.pdf` | `MHC-PS-RESERVED-JUDGMENT` | 1.00 | 16/31 | 4449 | serif, a4_page, watermark |
| `1ZIbM4Y7x6aBulC4zrnDFE6pbN5KffzNx_5fa6cbdda85934ede4da4fee2bba8fa68b4ceed1c78c04f3c97cb1edfc0b7ebd1791784468.pdf` | `MHC-MB-RESERVED-JUDGMENT` | 1.00 | 19/31 | 3492 | serif, a4_page, watermark |
| `1ZS9maJdaMoy9xziwZXS8rqZINyb5_KiX_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.85 | 14/27 | 2403 | serif, watermark |
| `1Znec3c-9eN1EnkfCndryP9qtRvKL5LNA_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.83 | 12/27 | 4475 | serif, a4_page, watermark |
| `1_qVc0dUzBVKl19aWTByW_ETAXTAMk1uv_HCMA013126442025.pdf` | `MHC-PS-CORAM-ORDER` | 0.88 | 14/30 | 1269 | serif, a4_page, watermark |
| `1cXFDTdOgWLvnZQN0fOvQanJTkwbh_qf-_CRL_MP_19193_2026.pdf` | `MHC-PS-CORAM-ORDER` | 0.88 | 13/30 | 4333 | serif, a4_page, watermark |
| `1g2qDZNduVUglmBZchRZtZdSH_k-kDs83_803f4f190ae56e8637b786c2f986c1c6d4e2885a9fa28cab085238fc4192ba411791784708.pdf` | `MHC-MB-CRIM-JURIS` | 1.00 | 16/29 | 4392 | mono_font |
| `1hL_8VV2NdVi_KhJ5SRcG-Cq6iglPL1RC_CMP_14931_2026.pdf` | `MHC-PS-CORAM-ORDER` | 0.84 | 9/30 | 610 | a4_page, watermark |
| `1j8y2U-aXg2c8r2uCrKxhHWgfuWeELYVC_8442afeb1e2244b884904652c3a36b7faa975e5e638e67858fece8cfa9e637d91791784701.pdf` | `MHC-PS-CORAM-ORDER` | 0.88 | 16/30 | 4318 | serif, a4_page, watermark |
| `1k7XIxsAnY3-lQd2O87IJa43ni5Fmg9le_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.85 | 11/27 | 1650 | serif, a4_page, watermark |
| `1kf0LAnSzWK6oTejgFn_V03sx78nKhy0h_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.85 | 14/27 | 2376 | serif, a4_page, watermark |
| `1n2eTkbLdaHw8veOGNNljO-X6OXzMXeeB_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CRIM-JURIS` | 0.90 | 15/29 | 554 | a4_page, watermark |
| `1oIhKGh7JSA_JslZUZt4_CX4rCZsRbVdi_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.85 | 13/27 | 1454 | serif, a4_page, watermark |
| `1pZHMvTogqoPOqOuir_3Xm7eXdvDH16Kg_CRL_MP_16662_2026.pdf` | `MHC-PS-CORAM-ORDER` | 0.88 | 15/30 | 2349 | serif, a4_page, watermark |
| `1qDqDQquIfGb3ddtO5LX-HjWsJQzr7QC5_A_3875_3876_2026.pdf` | `MHC-PS-RESERVED-JUDGMENT` | 0.93 | 19/31 | 4092 | serif, a4_page, watermark |
| `1raXnZIyqp9dlGLNfmirXFdnWElOEtaOi_HCMA010352822016.pdf` | `MHC-PS-CORAM-ORDER` | 0.88 | 14/30 | 1156 | serif, a4_page, watermark |
| `1tkVQ6c-2lvHaUMvMFqa_HvTBONFR8SEF_6bd803298bdd582f1a6a26b8a422e350db12a54a87c80e8523844d808b6d6d491791784757.pdf` | `MHC-MB-CORAM-ORDER` | 0.88 | 15/27 | 3170 | serif, a4_page, watermark |
| `1vf7HUOrqVH923saNTReX5TzOqVaBOk18_Home _ Judgements and Orders, Supreme Court and High courts of India.pdf` | `MHC-MB-CORAM-ORDER` | 0.85 | 10/27 | 1040 | serif, a4_page, watermark |
| `1x_ovr-42koCwngW7418hqIp_20s-Adkp_HCMA011880622026.pdf` | `MHC-PS-CORAM-ORDER` | 0.88 | 12/30 | 1850 | serif, a4_page, watermark |
| `03_wp-md-29011-2026.pdf` | `MHC-MB-CORAM-ORDER` | 0.88 | 15/27 | 1826 | a4_page, watermark |
| `28_cwp-1744-2024-ph.pdf` | `PHHC-CWP-COLUMNAR` | 0.76 | 18/30 | 4411 | legal_page, clipped_blocks, columnar |

