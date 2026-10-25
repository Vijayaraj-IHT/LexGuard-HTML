import os
import re

html_files = [
    r"e:\SEM 5 PROJECT\Lexguard\lexguard-html\case-viewer.html",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend\case-viewer.html",
]

js_files = [
    r"e:\SEM 5 PROJECT\Lexguard\lexguard-html\js\pages\case-viewer.js",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend\js\pages\case-viewer.js",
]

NEW_RIBBON_BUTTONS = """          <div class="d-flex align-items-center gap-2">
            <button class="btn btn-xs btn-outline-light" id="btn-open-seal-modal" data-bs-toggle="modal" data-bs-target="#digitalSealCertificateModal">
              <i class="bi bi-patch-check-fill text-warning me-1"></i>Digital Seal Certificate
            </button>
            <button class="btn btn-xs btn-outline-secondary text-light" id="btn-copy-citation" title="Copy Citation">
              <i class="bi bi-quote me-1"></i>Copy Citation
            </button>
            <a href="#" class="btn btn-xs btn-judicial-outline" id="case-verify-link">
              <i class="bi bi-search me-1"></i>Inspect Audit Chain
            </a>
          </div>"""

SEAL_MODAL_HTML = """  <!-- Digital Seal Certificate Modal (Printable Certified Copy Sheet) -->
  <div class="modal fade" id="digitalSealCertificateModal" tabindex="-1" aria-labelledby="digitalSealCertificateModalLabel" aria-hidden="true">
    <div class="modal-dialog modal-lg modal-dialog-centered">
      <div class="modal-content bg-white text-dark border-0 shadow-lg">
        <div class="modal-header bg-danger text-white border-0 py-3">
          <div class="d-flex align-items-center gap-2">
            <i class="bi bi-shield-shaded fs-4"></i>
            <div>
              <h5 class="modal-title font-serif fw-bold mb-0" id="digitalSealCertificateModalLabel">LEXGUARD JUDICIAL REPOSITORY</h5>
              <div class="small text-white-50">CERTIFIED DIGITAL RECORD OF JUDGMENT &bull; STATUTORY DIGITAL SEAL</div>
            </div>
          </div>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <div class="modal-body p-4" id="printable-certificate-content">
          <!-- Official Certificate Header -->
          <div class="text-center pb-3 border-bottom border-secondary border-opacity-25 mb-4">
            <div class="fs-4 font-serif fw-bold text-danger text-uppercase mb-1" id="cert-court-name">High Court of Judicature</div>
            <div class="text-muted small text-uppercase letter-spacing-1">Official Electronic Law Report &bull; Certified Copy Sheet</div>
            <div class="mt-2">
              <span class="badge bg-success px-3 py-1 font-mono fs-7"><i class="bi bi-check-circle-fill me-1"></i>VERIFIED UNALTERED RECORD</span>
            </div>
          </div>

          <!-- Case Identification Grid -->
          <div class="row g-3 mb-4">
            <div class="col-sm-6">
              <div class="p-3 bg-light rounded border">
                <div class="text-muted small text-uppercase fw-semibold">Case Title</div>
                <div class="fw-bold font-serif fs-6 mt-1" id="cert-case-title">—</div>
              </div>
            </div>
            <div class="col-sm-6">
              <div class="p-3 bg-light rounded border">
                <div class="text-muted small text-uppercase fw-semibold">Case Number &amp; CNR</div>
                <div class="fw-bold font-mono text-dark mt-1" id="cert-case-no">—</div>
                <div class="small font-mono text-secondary" id="cert-cnr-no">CNR: —</div>
              </div>
            </div>
            <div class="col-sm-6">
              <div class="p-3 bg-light rounded border">
                <div class="text-muted small text-uppercase fw-semibold">Bench &amp; Presiding Judge</div>
                <div class="fw-semibold text-dark mt-1" id="cert-judge-name">—</div>
                <div class="small text-muted" id="cert-bench-type">Division / Single Bench</div>
              </div>
            </div>
            <div class="col-sm-6">
              <div class="p-3 bg-light rounded border">
                <div class="text-muted small text-uppercase fw-semibold">Date of Decision &amp; Outcome</div>
                <div class="fw-bold text-dark mt-1" id="cert-decision-date">—</div>
                <div class="badge bg-danger mt-1" id="cert-outcome-badge">—</div>
              </div>
            </div>
          </div>

          <!-- Cryptographic Seal Information -->
          <div class="p-3 rounded border border-danger border-opacity-25 bg-danger bg-opacity-10 mb-4">
            <div class="d-flex align-items-center gap-2 mb-2">
              <i class="bi bi-patch-check-fill text-danger fs-5"></i>
              <div class="fw-bold font-serif text-danger">Cryptographic Integrity Seal (SHA-256 Digest)</div>
            </div>
            <div class="font-mono text-dark small text-break p-2 bg-white rounded border" id="cert-sha256-hash" style="font-size: 0.8rem;">
              —
            </div>
            <div class="d-flex justify-content-between align-items-center text-muted small mt-2">
              <span>Repository Status: <strong>VALIDATED</strong></span>
              <span id="cert-generated-timestamp">Generated: —</span>
            </div>
          </div>

          <!-- Statutory Certificate Clause -->
          <div class="p-3 rounded bg-light border text-secondary small mb-2" style="font-size: 0.78rem;">
            <strong>Statutory Admissibility Notice:</strong> This digital copy is generated from the certified LexGuard judicial corpus and authenticated under Section 65B of the Indian Evidence Act, 1872 / Section 63 of Bharatiya Sakshya Adhiniyam, 2023. The SHA-256 cryptographic fingerprint uniquely identifies and proves the unaltered integrity of this judicial record.
          </div>
        </div>
        <div class="modal-footer bg-light border-0 justify-content-between">
          <button type="button" class="btn btn-sm btn-outline-secondary" data-bs-dismiss="modal">Close</button>
          <div class="d-flex gap-2">
            <button type="button" class="btn btn-sm btn-outline-danger" id="cert-copy-hash-btn">
              <i class="bi bi-clipboard me-1"></i>Copy SHA-256
            </button>
            <button type="button" class="btn btn-sm btn-danger" onclick="window.print()">
              <i class="bi bi-printer me-1"></i>Print Certificate
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>"""

PRINT_CSS = """
  <style>
    @media print {
      body * {
        visibility: hidden !important;
      }
      #printable-certificate-content, #printable-certificate-content * {
        visibility: visible !important;
      }
      #printable-certificate-content {
        position: absolute !important;
        left: 0 !important;
        top: 0 !important;
        width: 100% !important;
        margin: 0 !important;
        padding: 20px !important;
        color: #000 !important;
        background: #fff !important;
      }
      .modal, .modal-dialog, .modal-content {
        position: static !important;
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
      }
    }
  </style>
"""

for hp in html_files:
    if not os.path.exists(hp):
        print(f"Skipping {hp}: not found")
        continue

    with open(hp, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. Replace the verify button in seal ribbon with ribbon buttons
    verify_btn_pattern = re.compile(r'<a\s+href="#"\s+class="btn\s+btn-xs\s+btn-judicial-outline"\s+id="case-verify-link">.*?</a>', re.DOTALL)
    if verify_btn_pattern.search(html):
        html = verify_btn_pattern.sub(NEW_RIBBON_BUTTONS, html)
        print(f"Updated seal ribbon buttons in {hp}")

    # 2. Add print CSS before </head> if not already added
    if "@media print" not in html:
        html = html.replace("</head>", f"{PRINT_CSS}\n</head>")
        print(f"Added print CSS in {hp}")

    # 3. Add modal before </body> if not already added
    if 'id="digitalSealCertificateModal"' not in html:
        html = html.replace("<!-- CDN JS Dependencies -->", f"{SEAL_MODAL_HTML}\n\n  <!-- CDN JS Dependencies -->")
        print(f"Added digital seal certificate modal in {hp}")

    with open(hp, "w", encoding="utf-8") as f:
        f.write(html)

# Update JS files
JS_CERT_LOGIC = """
    // Populate Digital Seal Certificate Modal
    $('#cert-court-name').text(c.court || 'High Court of Judicature');
    $('#cert-case-title').text(c.title || 'Untitled Judicial Case');
    $('#cert-case-no').text(c.case_no || '—');
    $('#cert-cnr-no').text(c.cnr_number ? ('CNR: ' + c.cnr_number) : (c.cnr ? ('CNR: ' + c.cnr) : 'CNR: Registered Under Judicial Repository'));
    $('#cert-judge-name').text(c.judge || 'Hon\'ble Judges of the Bench');
    $('#cert-bench-type').text((c.bench_type || 'Judicial Bench') + (c.legal_domain ? (' • ' + c.legal_domain) : ''));
    $('#cert-decision-date').text(LG.utils.formatDate(c.decision_date || c.created_at));
    $('#cert-outcome-badge').text(c.outcome || c.disposition || 'Disposed');
    $('#cert-sha256-hash').text(c.file_hash || 'SHA-256 Digest Pending');
    $('#cert-generated-timestamp').text('Generated: ' + new Date().toLocaleString('en-IN', { dateStyle: 'long', timeStyle: 'medium' }));
"""

JS_BUTTON_HANDLERS = """
    // Copy Official / Neutral Citation
    $('#btn-copy-citation').off('click').on('click', function (e) {
      e.preventDefault();
      if (!currentCase) return;
      const yr = currentCase.decision_date ? new Date(currentCase.decision_date).getFullYear() : (currentCase.year || 2026);
      const shortId = (currentCase.file_hash || currentCase.id || '').substring(0, 8);
      const citation = currentCase.official_citation || `${currentCase.title || 'Judgment'}, ${currentCase.case_no || ''} (${currentCase.court || 'Court'}, ${yr}) [LexGuard ID: ${shortId}]`;
      if (navigator.clipboard) {
        navigator.clipboard.writeText(citation).then(function () {
          if (window.LG && window.LG.toast) {
            window.LG.toast.success('Citation copied to clipboard!');
          }
        });
      }
    });

    // Copy SHA-256 Digest in Modal
    $('#cert-copy-hash-btn').off('click').on('click', function () {
      if (currentCase && currentCase.file_hash && navigator.clipboard) {
        navigator.clipboard.writeText(currentCase.file_hash).then(function () {
          if (window.LG && window.LG.toast) {
            window.LG.toast.success('SHA-256 cryptographic seal copied!');
          }
        });
      }
    });
"""

for jp in js_files:
    if not os.path.exists(jp):
        print(f"Skipping {jp}: not found")
        continue

    with open(jp, "r", encoding="utf-8") as f:
        js = f.read()

    if "#cert-court-name" not in js:
        target = "$sealHash.text('SHA-256 Digest Pending');\n    }"
        if target in js:
            js = js.replace(target, target + "\n" + JS_CERT_LOGIC)
            print(f"Added cert modal populate logic in {jp}")

    if "#btn-copy-citation" not in js:
        # Attach before renderOverviewTab
        target2 = "function renderOverviewTab(c) {"
        if target2 in js:
            js = js.replace(target2, JS_BUTTON_HANDLERS + "\n\n  " + target2)
            print(f"Added copy citation handlers in {jp}")

    with open(jp, "w", encoding="utf-8") as f:
        f.write(js)

print("Done updating case-viewer files.")
