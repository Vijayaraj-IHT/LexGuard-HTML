import os
import re

upload_html_files = [
    r"e:\SEM 5 PROJECT\Lexguard\lexguard-html\case-upload.html",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend\case-upload.html",
]

TAB_BTN = """        <li class="nav-item" role="presentation">
          <button class="nav-link bg-dark border border-secondary border-opacity-25 text-light fw-semibold" id="tab-batch-btn" data-bs-toggle="pill" data-bs-target="#tab-batch" type="button" role="tab">
            <i class="bi bi-folder-symlink text-success me-1"></i>Batch Ingestion Engine (Scale Corpus)
          </button>
        </li>
        <li class="nav-item" role="presentation">
          <button class="nav-link bg-dark border border-secondary border-opacity-25 text-light fw-semibold" id="tab-manual-btn" data-bs-toggle="pill" data-bs-target="#tab-manual" type="button" role="tab">"""

TAB_PANE = """        <!-- TAB 3: Batch Corpus Ingestion Engine -->
        <div class="tab-pane fade" id="tab-batch" role="tabpanel">
          <div class="card card-judicial p-4 mb-4 shadow">
            <div class="d-flex align-items-center justify-content-between mb-3">
              <div>
                <h2 class="h5 fw-bold text-light mb-1"><i class="bi bi-server text-success me-2"></i>Batch Ingestion &amp; Citation Linker Engine</h2>
                <p class="text-secondary small mb-0">
                  Bulk ingests multiple downloaded court judgments into the certified corpus, computes SHA-256 seals, extracts CNRs, and cross-links the precedent citation network.
                </p>
              </div>
              <span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-25 px-3 py-2">
                <i class="bi bi-cpu-fill me-1"></i>High-Throughput Mode
              </span>
            </div>

            <!-- Workflow Guide -->
            <div class="row g-3 mb-4">
              <div class="col-md-4">
                <div class="p-3 rounded bg-dark border border-secondary border-opacity-25 h-100">
                  <div class="fw-bold text-warning small mb-1"><i class="bi bi-1-circle-fill me-1"></i>Drop Target Directory</div>
                  <div class="small text-secondary">
                    Save downloaded authentic PDFs to <code class="text-light">incoming_pdfs/</code> in the project root.
                  </div>
                </div>
              </div>
              <div class="col-md-4">
                <div class="p-3 rounded bg-dark border border-secondary border-opacity-25 h-100">
                  <div class="fw-bold text-info small mb-1"><i class="bi bi-2-circle-fill me-1"></i>Automated Ingestion</div>
                  <div class="small text-secondary">
                    Executes text sanitization, coram extraction, and SHA-256 judicial file renaming.
                  </div>
                </div>
              </div>
              <div class="col-md-4">
                <div class="p-3 rounded bg-dark border border-secondary border-opacity-25 h-100">
                  <div class="fw-bold text-success small mb-1"><i class="bi bi-3-circle-fill me-1"></i>Citation Graph Linker</div>
                  <div class="small text-secondary">
                    Automatically connects cited precedents and updates <code class="text-light">cited_by_count</code> across the repository.
                  </div>
                </div>
              </div>
            </div>

            <!-- Command line shortcut & CLI trigger -->
            <div class="p-3 rounded bg-dark border border-secondary border-opacity-30 mb-3 font-mono small">
              <div class="text-secondary small mb-1">Command-Line Batch Pipeline:</div>
              <div class="text-warning user-select-all">python scripts/batch_ingest_judgments.py</div>
            </div>

            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 pt-2 border-top border-secondary border-opacity-20">
              <span class="small text-secondary"><i class="bi bi-info-circle me-1"></i>Deduplication is guaranteed via cryptographic SHA-256 fingerprinting.</span>
              <a href="search.html" class="btn btn-sm btn-gold">
                <i class="bi bi-search me-1"></i>Explore Indexed Corpus
              </a>
            </div>
          </div>
        </div>
"""

for hp in upload_html_files:
    if not os.path.exists(hp):
        continue
    with open(hp, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. Add tab button
    manual_btn_target = '<li class="nav-item" role="presentation">\n          <button class="nav-link bg-dark border border-secondary border-opacity-25 text-light fw-semibold" id="tab-manual-btn" data-bs-toggle="pill" data-bs-target="#tab-manual" type="button" role="tab">'
    if "tab-batch-btn" not in html:
        if manual_btn_target in html:
            html = html.replace(manual_btn_target, TAB_BTN)
            print(f"Added batch tab button in {hp}")

    # 2. Add tab pane before manual tab pane
    manual_pane_target = '<!-- TAB 2: Manual Ingestion -->'
    if 'id="tab-batch"' not in html:
        if manual_pane_target in html:
            html = html.replace(manual_pane_target, TAB_PANE + "\n        " + manual_pane_target)
            print(f"Added batch tab pane in {hp}")

    with open(hp, "w", encoding="utf-8") as f:
        f.write(html)

print("Batch upload UI updates complete.")
