    const items = [
      // Phase 2 (HTML5 - Court Red & White Theme)
      { id: "html_00", phase: "phase2", tags: ["search", "auth"], title: "High Court Portal & 10-Service Grid", filename: "html_00_landing.png", desc: "Official Madras High Court e-Courts portal with CNR search hero, trust statistics, and 10 judicial service tiles in Court Red & White theme." },
      { id: "html_01", phase: "phase2", tags: ["auth"], title: "Multi-Role Quick Access Login", filename: "html_01_login.png", desc: "Zero-build Bootstrap 5 login with instant one-click test credentials for Staff, Advocate, Scholar, and Public." },
      { id: "html_02", phase: "phase2", tags: ["auth"], title: "Citizen & Bar Registration", filename: "html_02_register.png", desc: "Pure HTML5/Bootstrap registration form with client-side validation, clean white panels, and crimson accents." },
      { id: "html_03", phase: "phase2", tags: ["search"], title: "Hybrid Precedent Search & Live DB", filename: "html_03_search_results.png", desc: "Precedent search querying live PostgreSQL database (208 cases) with match confidence percentage and citation copy." },
      { id: "html_04", phase: "phase2", tags: ["review"], title: "Staff Analytics & Approval Queue", filename: "html_04_dashboard_admin.png", desc: "Live Chart.js doughnut & bar charts in crimson palette with one-click verification queue actions on PostgreSQL." },
      { id: "html_05", phase: "phase2", tags: ["search"], title: "Advanced PDF.js Viewer & Dossier", filename: "html_05_case_viewer_pdf.png", desc: "Split-view PDF reader with selectable text layer, thumbnail navigation drawer, keyword search stepper, and print." },
      { id: "html_06", phase: "phase2", tags: ["review"], title: "Split-Screen Staff CIS Review", filename: "html_06_case_review_split.png", desc: "Draggable split-screen reviewer with PDF on the left and live editable CIS fields (FIR, Police Station, Acts) on the right." },
      { id: "html_07", phase: "phase2", tags: ["compare"], title: "3-Precedent Tray & Concordance", filename: "html_07_case_compare_tray.png", desc: "Multi-case comparison tray supporting up to 3 precedents alongside CrPC 1973 ↔ BNSS 2023 concordance matrix." },
      { id: "html_08", phase: "phase2", tags: ["compare"], title: "AI Judgment Draft Assistant Studio", filename: "html_08_draft_assistant.png", desc: "Interactive draft studio with draggable split resizer, saved draft sessions modal, and precision statutory audit." },
      { id: "html_09", phase: "phase2", tags: ["statutory"], title: "Major Indian Acts Catalog", filename: "html_09_acts_explorer.png", desc: "Categorized statutory directory covering IPC, CrPC, Evidence Act, BNS, BNSS, and BSA with instant section search." },
      { id: "html_10", phase: "phase2", tags: ["crypto"], title: "SHA-256 Tamper Verification Engine", filename: "html_10_verify_tamper.png", desc: "Web Crypto API SHA-256 client hashing and backend database ledger lookup for tamper detection." },
      { id: "html_11", phase: "phase2", tags: ["search"], title: "Madras HC Daily Cause List Tracker", filename: "html_11_cause_list.png", desc: "Principal Seat & Madurai Bench court board tracker with live courtroom status and case serial listing." },
      { id: "html_12", phase: "phase2", tags: ["crypto"], title: "Cryptographic System Audit Register", filename: "html_12_audit_ledger.png", desc: "Dedicated Merkle hash-chained ledger viewer with live SHA-256 block hash inspector and chain verification against PostgreSQL." },
      { id: "html_13", phase: "phase2", tags: ["search"], title: "Upgraded Case Reader & Keyword Finder", filename: "html_13_case_viewer_upgraded.png", desc: "Binary PDF.js stream reader with integrated in-document keyword extraction, page pills, and official judicial brief export." },
      { id: "html_14", phase: "phase2", tags: ["errors"], title: "Judicial 404 Not Found Portal", filename: "html_14_404_page.png", desc: "Light judicial 404 error page with live case search input, direct links to statutory explorer and staff portal, and route diagnostics." },
      { id: "html_15", phase: "phase2", tags: ["search"], title: "Live Daily Cause List & Court Board", filename: "html_15_cause_list_live.png", desc: "Principal Seat & Madurai Bench court board tracker querying live PostgreSQL cases with status pills and dossier shortcuts." },
      { id: "html_16", phase: "phase2", tags: ["errors"], title: "Graceful 404 Docket Handler in Viewer", filename: "html_16_case_viewer_404.png", desc: "In-line judicial empty state when an invalid or sealed case identifier is requested, preventing hanging spinners." },

      // Phase 1 (React)
      { id: "react_01", phase: "phase1", tags: ["auth"], title: "Landing Page & e-Courts Grid", filename: "react_01_landing.png", desc: "React Landing page featuring e-Courts service grid, Madras High Court bench quick links, and system architecture metrics." },
      { id: "react_02", phase: "phase1", tags: ["auth"], title: "Staff & Advocate Sign In", filename: "react_02_login.png", desc: "React Auth page with dual credentials, quick demo persona chips (Registrar, Advocate, Scholar), and JWT session issuance." },
      { id: "react_03", phase: "phase1", tags: ["auth"], title: "User & Bar Registration", filename: "react_03_register.png", desc: "Role-based registration with bar council enrollment verification and academic institution validation." },
      { id: "react_04", phase: "phase1", tags: ["search"], title: "Precedent Hybrid Search", filename: "react_04_search_public.png", desc: "InLegalBERT semantic and BM25 full-text hybrid search interface with RRF ranking across Madras High Court cases." },
      { id: "react_05", phase: "phase1", tags: ["statutory"], title: "Statutory Acts & BNS Concordance", filename: "react_05_acts_explorer.png", desc: "Interactive statutory explorer mapping Indian Penal Code to Bharatiya Nyaya Sanhita (BNS) 2023 with section search." },
      { id: "react_06", phase: "phase1", tags: ["crypto"], title: "SHA-256 Tamper Verification", filename: "react_06_verify_public.png", desc: "Cryptographic hash verification portal for calculating file digests and auditing tamper-evident digital seals." },
      { id: "react_07", phase: "phase1", tags: ["review"], title: "Staff Executive Dashboard", filename: "react_07_dashboard_staff.png", desc: "Registrar executive dashboard with KPI metrics, ingest velocity, pending approval count, and distribution charts." },
      { id: "react_08", phase: "phase1", tags: ["search"], title: "Authenticated Case Search", filename: "react_08_search_auth.png", desc: "Advocate research workspace with citation bookmarking, judgment export, and court filters." },
      { id: "react_09", phase: "phase1", tags: ["search"], title: "Judicial Case Reader & Dossier", filename: "react_09_case_viewer.png", desc: "Comprehensive case dossier with Coram details, decision dates, disposition badges, and SHA-256 integrity seal." },
      { id: "react_10", phase: "phase1", tags: ["review"], title: "Human-in-the-Loop CIS Review", filename: "react_10_case_review.png", desc: "Court Staff moderation desk verifying extracted CIS docket fields, police station, FIR, and statutory sections." },
      { id: "react_11", phase: "phase1", tags: ["compare"], title: "Multi-Case Comparative Matrix", filename: "react_11_case_compare.png", desc: "Comparative precedent workbench analyzing holding divergence, ratio decidendi, and legal issue concordance." },
      { id: "react_12", phase: "phase1", tags: ["crypto"], title: "Cryptographic System Audit Register", filename: "react_12_audit_ledger.png", desc: "Immutable SHA-256 chained audit logs tracking all case modifications, verifications, and approvals." },
      { id: "react_13", phase: "phase1", tags: ["review"], title: "Case Ingestion & CIS Extraction", filename: "react_13_case_upload.png", desc: "PDF upload pipeline with automated InLegalBERT NER extraction and cryptographic hashing." },
      { id: "react_14", phase: "phase1", tags: ["errors"], title: "Tailwind & Lucide 404 Recovery Screen", filename: "react_14_404_page.png", desc: "User-friendly React 404 page with route diagnostics, in-card precedent search, and fast navigation links." }
    ];

    function renderGallery(filter) {
      const $container = $('#gallery-container');
      $container.empty();

      const filtered = items.filter(item => {
        if (filter === 'all') return true;
        if (filter === 'phase1') return item.phase === 'phase1';
        if (filter === 'phase2') return item.phase === 'phase2';
        return item.tags.includes(filter);
      });

      filtered.forEach(item => {
        const phaseBadge = item.phase === 'phase1' 
          ? '<span class="status-pill badge-phase1"><i class="bi bi-code-slash me-1"></i>Phase 1 (React)</span>'
          : '<span class="status-pill badge-phase2"><i class="bi bi-filetype-html me-1"></i>Phase 2 (HTML5)</span>';

        const cardHtml = `
          <div class="col-md-6 col-lg-4 col-xl-3">
            <div class="gallery-card h-100 d-flex flex-column">
              <img src="screenshots/${item.filename}" alt="${item.title}" class="gallery-img" data-title="${item.title}" data-desc="${item.desc}" data-src="screenshots/${item.filename}">
              <div class="p-3 d-flex flex-column flex-grow-1">
                <div class="d-flex align-items-center justify-content-between mb-2">
                  ${phaseBadge}
                  <span class="badge bg-light text-danger border border-danger border-opacity-25">${item.tags[0]}</span>
                </div>
                <h6 class="fw-bold text-dark mb-1 font-serif">${item.title}</h6>
                <p class="small text-secondary flex-grow-1 mb-3">${item.desc}</p>
                <div class="d-flex align-items-center justify-content-between pt-2 border-top border-danger border-opacity-10">
                  <span class="small text-muted font-monospace" style="font-size: 0.7rem;">${item.filename}</span>
                  <button class="btn btn-sm btn-outline-danger view-btn" data-title="${item.title}" data-desc="${item.desc}" data-src="screenshots/${item.filename}">
                    <i class="bi bi-arrows-fullscreen"></i>
                  </button>
                </div>
              </div>
            </div>
          </div>
        `;
        const $card = $(cardHtml);
        $container.append($card);
        // Replaces the former inline onerror attribute: fall back once to a known image.
        $card.find('img.gallery-img').on('error', function () {
          if (!this.dataset.fellBack) {
            this.dataset.fellBack = '1';
            this.src = 'screenshots/html_03_search_results.png';
          }
        });
      });

      // Bind modal triggers
      $('.gallery-img, .view-btn').on('click', function() {
        const title = $(this).data('title');
        const desc = $(this).data('desc');
        const src = $(this).data('src');

        $('#modalTitle').text(title);
        $('#modalDesc').text(desc);
        $('#modalImg').attr('src', src);
        $('#modalDownload').attr('href', src).attr('download', src.split('/').pop());

        const modal = new bootstrap.Modal(document.getElementById('imageModal'));
        modal.show();
      });
    }

    $(document).ready(function() {
      renderGallery('all');

      $('.filter-btn').on('click', function() {
        $('.filter-btn').removeClass('active');
        $(this).addClass('active');
        const f = $(this).data('filter');
        renderGallery(f);
      });
    });
