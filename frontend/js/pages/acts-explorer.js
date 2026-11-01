/**
 * LexGuard — Statutory & Acts Explorer Controller (acts-explorer.js)
 * Live Codified Bare Acts, Judicial Commentary, and Case Precedent Linker
 */

$(document).ready(function () {
  'use strict';

  const $container = $('#acts-catalog-container');
  const $searchInput = $('#acts-search-input');
  const modalEl = document.getElementById('statute-detail-modal');
  const statuteModal = modalEl ? new bootstrap.Modal(modalEl) : null;

  let liveActsData = [];

  // Fallback metadata for badges and categories
  const ACT_METADATA = {
    'CRPC': { category: 'Criminal Procedure', badgeClass: 'badge-court-madras', newEquiv: 'BNSS, 2023', desc: 'Governs investigations, regular/anticipatory bail, and inherent quashing powers under Section 482.' },
    'IPC': { category: 'Substantive Criminal Law', badgeClass: 'badge-court-madurai', newEquiv: 'BNS, 2023', desc: 'Defines offences including murder, cheating, cruelty, and statutory criminal liabilities.' },
    'CONST': { category: 'Constitutional Law', badgeClass: 'badge-court-supreme', newEquiv: null, desc: 'Supreme constitutional charter guaranteeing fundamental rights and extraordinary High Court writ review under Article 226.' },
    'NI_ACT': { category: 'Commercial Banking', badgeClass: 'badge-gold', newEquiv: null, desc: 'Strict statutory regime governing cheque dishonour, statutory demand notices, and Section 139 legal presumptions.' },
    'NDPS': { category: 'Special Criminal Law', badgeClass: 'badge-court-madras', newEquiv: null, desc: 'Stringent procedural safeguards and rigorous Section 37 bail twin conditions for commercial narcotic seizures.' },
    'ARB': { category: 'Commercial Arbitration', badgeClass: 'badge-gold', newEquiv: null, desc: 'Section 9 interim court protections and Section 34 patent illegality challenge thresholds against arbitral awards.' },
    'IEA': { category: 'Law of Evidence', badgeClass: 'badge-court-madurai', newEquiv: 'BSA, 2023', desc: 'Admissibility of electronic records under Section 65B, dying declarations, and evidentiary burdens.' },
    'POCSO': { category: 'Child Protection Law', badgeClass: 'badge-court-madras', newEquiv: null, desc: 'Rigorous statutory presumption of guilt under Section 29 and specialized trial procedures for minor protection.' },
    'PMLA': { category: 'Financial Crime Enforcement', badgeClass: 'badge-court-supreme', newEquiv: null, desc: 'Enforcement Directorate investigations, attachment of crime proceeds, and Section 45 twin bail rigors.' },
    'SRA': { category: 'Civil Equity Law', badgeClass: 'badge-court-madras', newEquiv: null, desc: 'Personal bars to specific performance and Section 16(c) continuous readiness and willingness proof.' },
    'CPC': { category: 'Civil Procedure', badgeClass: 'badge-court-madurai', newEquiv: null, desc: 'Code of Civil Procedure governing Section 100 second appeals and Order 39 interim temporary injunctions.' },
    'PCA': { category: 'Anti-Corruption Law', badgeClass: 'badge-court-supreme', newEquiv: null, desc: 'Prevention of Corruption Act requiring Section 19 prior sanction to protect public servants from vexatious prosecution.' }
  };

  /**
   * Fetch live acts and codified sections from FastAPI backend.
   */
  function fetchActsCatalog() {
    $container.html(`
      <div class="card card-judicial text-center p-5">
        <div class="spinner-border text-danger mb-3" role="status"></div>
        <h4 class="h6 text-light mb-0">Loading Codified Indian Bare Acts &amp; Statutes...</h4>
      </div>
    `);

    const apiUrl = LG.config.API_BASE + '/statutes/acts';
    $.getJSON(apiUrl)
      .done(function (acts) {
        liveActsData = acts || [];
        renderCatalog();

        // Check if opened with URL query params: ?act=CRPC&section=482
        const params = new URLSearchParams(window.location.search);
        const urlAct = params.get('act');
        const urlSec = params.get('section');
        if (urlAct && urlSec) {
          openSectionDetail(urlAct, urlSec);
        }
      })
      .fail(function () {
        $container.html(`
          <div class="card card-judicial text-center p-4">
            <i class="bi bi-exclamation-triangle text-danger fs-3 mb-2"></i>
            <h5 class="text-light">Failed to load codified statutes</h5>
            <p class="text-secondary small">Please ensure the backend daemon on port 8000 is active.</p>
          </div>
        `);
      });
  }

  /**
   * Render Acts Catalog.
   */
  function renderCatalog(filterQuery) {
    $container.empty();
    const q = (filterQuery || '').toLowerCase().trim();

    liveActsData.forEach(function (act) {
      const meta = ACT_METADATA[act.act_code] || {
        category: 'Indian Statute',
        badgeClass: 'badge-court-madras',
        newEquiv: null,
        desc: act.act_title
      };

      // Filter sections
      const matchedSections = (act.sections || []).filter(function (s) {
        if (!q) return true;
        return (
          act.act_code.toLowerCase().includes(q) ||
          act.act_title.toLowerCase().includes(q) ||
          (meta.newEquiv && meta.newEquiv.toLowerCase().includes(q)) ||
          s.section_no.toLowerCase().includes(q) ||
          s.section_title.toLowerCase().includes(q)
        );
      });

      if (matchedSections.length === 0) return;

      const actHtml = `
        <div class="lg-statute-card shadow mb-4">
          <div class="d-flex align-items-start justify-content-between flex-wrap gap-2 mb-2 pb-2 border-bottom border-secondary border-opacity-25">
            <div>
              <div class="d-flex align-items-center gap-2 mb-1">
                <span class="badge ${meta.badgeClass}">${meta.category}</span>
                ${meta.newEquiv ? `<span class="badge badge-court-red"><i class="bi bi-arrow-repeat me-1"></i>${meta.newEquiv}</span>` : ''}
                <span class="badge bg-secondary">${act.total_cases || 0} Cases Indexed</span>
              </div>
              <h2 class="h5 fw-bold text-dark mb-1">${LG.utils.escapeHtml(act.act_title)}</h2>
              <p class="text-secondary small mb-0">${LG.utils.escapeHtml(meta.desc)}</p>
            </div>
            <div>
              <a href="search.html?q=${encodeURIComponent(act.act_title)}" class="btn btn-xs btn-judicial-outline">
                <i class="bi bi-search me-1"></i>Search All in Precedents
              </a>
            </div>
          </div>

          <div class="row g-3 mt-1">
            ${matchedSections.map(function (s) {
              return `
                <div class="col-md-6">
                  <div class="lg-statute-section-item section-click-card" data-act="${act.act_code}" data-section="${s.section_no}" style="cursor: pointer;">
                    <div class="d-flex align-items-center justify-content-between mb-1">
                      <span class="fw-bold text-danger font-mono">
                        <i class="bi bi-bookmark-fill me-1 text-danger"></i>Section ${LG.utils.escapeHtml(s.section_no)}
                      </span>
                      <span class="badge bg-light text-danger border border-danger border-opacity-25 small">
                        ${s.case_count || 0} Judgments <i class="bi bi-chevron-right ms-1"></i>
                      </span>
                    </div>
                    <div class="fw-bold text-dark small mb-1">${LG.utils.escapeHtml(s.section_title)}</div>
                    <div class="text-secondary small lh-sm" style="font-size: 0.8rem;">
                      Click to inspect official codified text &amp; matching High Court rulings.
                    </div>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;

      $container.append(actHtml);
    });

    // Attach click events to section cards
    $('.section-click-card').on('click', function () {
      const actCode = $(this).data('act');
      const secNo = $(this).data('section');
      openSectionDetail(actCode, secNo);
    });

    if ($container.children().length === 0) {
      $container.html(`
        <div class="card card-judicial text-center p-5">
          <i class="bi bi-search text-secondary display-6 mb-3"></i>
          <h3 class="h5 text-light">No matching statutory sections found</h3>
          <p class="text-secondary small mb-0">Try searching for generic terms like "CrPC", "bail", "quashing", or section numbers like "482".</p>
        </div>
      `);
    }
  }

  /**
   * Opens the Codified Bare Act Section Modal and displays legislative text + linked cases.
   */
  function openSectionDetail(actCode, secNo) {
    if (!statuteModal) return;

    $('#modal-act-code').text(actCode);
    $('#modal-section-title').text(`Section ${secNo}`);
    $('#modal-act-title').text('Loading legislative details...');
    $('#modal-bare-text').text('Loading official legislative bare text...');
    $('#modal-explanation').text('Loading judicial commentary...');
    $('#modal-cases-list').html('<div class="spinner-border spinner-border-sm text-warning" role="status"></div> Loading cases...');
    $('#modal-search-all-link').attr('href', `search.html?q=Section+${secNo}+${actCode}`);

    statuteModal.show();

    const baseApi = LG.config.API_BASE;
    $.getJSON(`${baseApi}/statutes/${encodeURIComponent(actCode)}/${encodeURIComponent(secNo)}`)
      .done(function (data) {
        $('#modal-section-title').text(`Section ${data.section_no}: ${data.section_title}`);
        $('#modal-act-title').text(data.act_title);
        $('#modal-bare-text').text(data.bare_text || 'Bare act text not available.');
        $('#modal-explanation').text(data.explanation || 'Judicial commentary under collation.');
        $('#modal-cases-count').text(data.cases ? data.cases.length : 0);

        const $list = $('#modal-cases-list');
        $list.empty();

        if (data.cases && data.cases.length > 0) {
          data.cases.forEach(function (c) {
            const item = $(`
              <div class="card p-3 bg-dark border-secondary border-opacity-25 hover-border-warning">
                <div class="d-flex align-items-start justify-content-between flex-wrap gap-2 mb-1">
                  <div>
                    <span class="badge bg-secondary mb-1" style="font-size: 0.7rem;">${LG.utils.escapeHtml(c.court || '')}</span>
                    <span class="badge bg-danger mb-1" style="font-size: 0.7rem;">${LG.utils.escapeHtml(c.case_type || 'Judgment')}</span>
                    <h6 class="text-light fw-bold mb-0">
                      <a href="case-viewer.html?id=${encodeURIComponent(c.id)}" class="text-light text-decoration-none hover-text-warning" target="_blank">
                        ${LG.utils.escapeHtml(c.title || c.case_no)}
                      </a>
                    </h6>
                  </div>
                  <div>
                    <span class="badge badge-gold" style="font-size: 0.7rem;">${LG.utils.escapeHtml(c.outcome || 'Disposed')}</span>
                  </div>
                </div>
                ${c.ratio_decidendi ? `<div class="small text-secondary fst-italic lh-sm mb-2" style="font-size: 0.78rem;">${LG.utils.escapeHtml(c.ratio_decidendi)}...</div>` : ''}
                <div class="d-flex align-items-center justify-content-between pt-1 border-top border-secondary border-opacity-10">
                  <span class="font-mono text-warning small" style="font-size: 0.72rem;">Case No: ${LG.utils.escapeHtml(c.case_no)}</span>
                  <a href="case-viewer.html?id=${encodeURIComponent(c.id)}" class="btn btn-xs btn-gold" target="_blank">
                    Open Case Viewer &rarr;
                  </a>
                </div>
              </div>
            `);
            $list.append(item);
          });
        } else {
          $list.html(`
            <div class="text-secondary small fst-italic p-3 text-center bg-dark rounded border border-secondary border-opacity-15">
              No direct cases indexed yet for Section ${secNo}. You can search related precedents in the search catalog.
            </div>
          `);
        }
      })
      .fail(function () {
        $('#modal-bare-text').text('Error loading codified text.');
        $('#modal-explanation').text('Unable to retrieve judicial commentary from backend.');
        $('#modal-cases-list').html('<div class="text-danger small">Failed to load linked cases.</div>');
      });
  }

  // Real-time Search Filter Handler
  $searchInput.on('input propertychange', function () {
    renderCatalog($(this).val());
  });

  // Initial Load
  fetchActsCatalog();
});
