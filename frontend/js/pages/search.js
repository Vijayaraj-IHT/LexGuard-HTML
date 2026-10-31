/**
 * LexGuard — Hybrid Precedent Search Page Controller (search.js)
 * LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  let currentQuery = '';
  let currentPage = 1;
  const pageSize = 10;
  let totalResults = 0;
  let activeSearchXhr = null;
  let debounceTimer = null;

  const $form = $('#search-form');
  const $input = $('#search-query-input');
  const $submitBtn = $('#search-submit-btn');
  const $loading = $('#search-loading');
  const $resultsContainer = $('#results-container');
  const $resultsCount = $('#results-count');
  const $paginationNav = $('#pagination-nav');
  const $paginationList = $('#pagination-list');
  const $understandingBox = $('#query-understanding-box');
  const $understandingDetails = $('#query-understanding-details');

  // Filter Elements
  const $filterCourt = $('#filter-court');
  const $filterYearFrom = $('#filter-year-from');
  const $filterYearTo = $('#filter-year-to');
  const $filterAct = $('#filter-act');
  const $filterOutcome = $('#filter-outcome');
  const $applyFiltersBtn = $('#apply-filters-btn');
  const $resetFiltersBtn = $('#reset-filters-btn');

  /**
   * Build filters object from UI inputs.
   */
  function buildFilters() {
    const filters = {};
    const court = $filterCourt.val();
    if (court) filters.court = court;

    const yf = parseInt($filterYearFrom.val(), 10);
    if (!isNaN(yf)) filters.year_from = yf;

    const yt = parseInt($filterYearTo.val(), 10);
    if (!isNaN(yt)) filters.year_to = yt;

    const act = $filterAct.val().trim();
    if (act) filters.act = act;

    const outcome = $filterOutcome.val();
    if (outcome) filters.outcome = outcome;

    const domain = $('#filter-domain').val();
    if (domain) filters.legal_domain = domain;

    const caseType = $('#filter-casetype').val();
    if (caseType) filters.case_type = caseType;

    return Object.keys(filters).length > 0 ? filters : null;
  }

  /**
   * Perform search query against backend.
   */
  function executeSearch(page) {
    page = page || 1;
    currentPage = page;
    const offset = (page - 1) * pageSize;

    $loading.removeClass('d-none');
    $resultsContainer.empty();
    $paginationNav.addClass('d-none');
    $understandingBox.addClass('d-none');

    const payload = {
      query: currentQuery,
      limit: pageSize,
      offset: offset
    };

    const filters = buildFilters();
    if (filters) {
      payload.filters = filters;
    }

    if (activeSearchXhr && activeSearchXhr.abort) {
      activeSearchXhr.abort();
    }
    activeSearchXhr = LG.api.search.query(payload)
    activeSearchXhr
      .done(function (res) {
        totalResults = res.total || 0;
        $resultsCount.text(totalResults);
        if (totalResults > 0) {
          $('#total-cases-badge').text(`${totalResults} Indexed Judgments`);
        }

        // Render InLegalBERT query understanding if present
        if (res.query_understanding && (res.query_understanding.statutory_sections?.length || res.query_understanding.legal_issues?.length)) {
          const sections = (res.query_understanding.statutory_sections || []).join(', ');
          const issues = (res.query_understanding.legal_issues || []).join('; ');
          let detailsText = '';
          if (sections) detailsText += `<strong>Identified Sections:</strong> ${LG.utils.escapeHtml(sections)} &nbsp;|&nbsp; `;
          if (issues) detailsText += `<strong>Issues:</strong> ${LG.utils.escapeHtml(issues)}`;
          $understandingDetails.html(detailsText);
          $understandingBox.removeClass('d-none');
        }

        if (!res.results || res.results.length === 0) {
          $resultsContainer.html(`
            <div class="card card-judicial text-center p-5">
              <i class="bi bi-search text-secondary display-6 mb-3"></i>
              <h5 class="text-light">No matching precedents found</h5>
              <p class="text-secondary small mb-0">Try broader legal terms, removing filter constraints, or searching by exact section number.</p>
            </div>
          `);
          return;
        }

        renderResults(res.results);
        renderPagination(totalResults, page);
      })
      .fail(function (xhr) {
        let msg = 'Failed to load search results.';
        if (xhr.responseJSON && xhr.responseJSON.detail) {
          msg = typeof xhr.responseJSON.detail === 'string'
            ? xhr.responseJSON.detail
            : JSON.stringify(xhr.responseJSON.detail);
        }
        $resultsContainer.html(`
          <div class="alert alert-danger p-4 text-center">
            <i class="bi bi-exclamation-triangle-fill fs-3 me-2"></i>
            <div>${LG.utils.escapeHtml(msg)}</div>
          </div>
        `);
      })
      .always(function () {
        $loading.addClass('d-none');
      });
  }

  /**
   * Render list of search result cards.
   */
  function renderResults(results) {
    const html = results.map(function (item) {
      const scorePct = Math.round((item.relevance_score || 0) * 100);
      const courtBadge = LG.utils.courtBadgeClass(item.court);
      const citationText = `${item.title}, (${item.year}) ${item.court}`;

      // Snippets
      let snippetHtml = '';
      if (item.matched_snippets && item.matched_snippets.length > 0) {
        snippetHtml = `
          <div class="case-snippet">
            ${item.matched_snippets.map(s => `<p class="mb-1">${s}</p>`).join('')}
          </div>
        `;
      } else if (item.summary) {
        snippetHtml = `<div class="case-snippet text-secondary">${LG.utils.escapeHtml(item.summary.substring(0, 240))}...</div>`;
      }

      // Tags (Acts & Sections)
      let tagsHtml = '';
      const acts = item.act_tags || [];
      const sections = item.section_tags || [];
      const allTags = acts.concat(sections).slice(0, 6);
      if (allTags.length > 0) {
        tagsHtml = `
          <div class="d-flex flex-wrap gap-1 mb-3">
            ${allTags.map(t => `<span class="badge bg-light text-danger border border-danger border-opacity-25">${LG.utils.escapeHtml(t)}</span>`).join('')}
          </div>
        `;
      }

      return `
        <div class="lg-case-card">
          <div class="d-flex align-items-start justify-content-between gap-3 mb-2">
            <div>
              <a href="case-viewer.html?id=${encodeURIComponent(item.id)}" class="case-title">
                ${LG.utils.escapeHtml(item.title)}
              </a>
              <div class="d-flex flex-wrap align-items-center gap-2 mt-1">
                                <span class="${courtBadge}">${LG.utils.escapeHtml(item.court)}</span>
                ${item.case_type ? `<span class="badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25">${LG.utils.escapeHtml(item.case_type)}</span>` : ''}
                <span class="badge bg-secondary">${item.year}</span>
                ${item.outcome ? `<span class="badge badge-gold">${LG.utils.escapeHtml(item.outcome)}</span>` : ''}
                ${item.precedential_status ? `<span class="badge bg-success bg-opacity-15 text-success border border-success border-opacity-30" style="font-size: 0.72rem;"><i class="bi bi-shield-check me-1"></i>${LG.utils.escapeHtml(item.precedential_status)}</span>` : ''}
                ${item.cited_by_count > 0 ? `<span class="badge bg-warning bg-opacity-15 text-warning border border-warning border-opacity-30" style="font-size: 0.72rem;"><i class="bi bi-diagram-3 me-1"></i>Cited in ${item.cited_by_count}</span>` : ''}
                ${item.official_citation ? `<span class="badge bg-dark text-warning border border-secondary border-opacity-25 font-mono" style="font-size: 0.7rem;">${LG.utils.escapeHtml(item.official_citation)}</span>` : ''}
                ${item.cnr_number ? `<span class="badge bg-dark text-light font-mono border border-secondary border-opacity-25" style="font-size: 0.7rem;"><i class="bi bi-upc-scan me-1"></i>${LG.utils.escapeHtml(item.cnr_number)}</span>` : ''}
                ${item.judge ? `<span class="small text-secondary"><i class="bi bi-person-fill me-1"></i>${LG.utils.escapeHtml(item.judge)}</span>` : ''}
              </div>
            </div>

            <!-- Relevance Score Badge -->
            <div class="text-end">
              <span class="badge ${scorePct >= 70 ? 'bg-success' : 'bg-primary'} fs-7 px-2 py-1" title="RRF Match Confidence">
                <i class="bi bi-graph-up-arrow me-1"></i>${scorePct}% Match
              </span>
            </div>
          </div>

          ${snippetHtml}
          ${tagsHtml}

          <!-- Card Actions Bar -->
          <div class="d-flex align-items-center justify-content-between pt-2 border-top border-secondary border-opacity-15 flex-wrap gap-2">
            <div class="d-flex align-items-center gap-2">
              <a href="case-viewer.html?id=${encodeURIComponent(item.id)}" class="btn btn-sm btn-gold">
                <i class="bi bi-book-half me-1"></i>Read Judgment
              </a>
              <a href="case-compare.html?case1=${encodeURIComponent(item.id)}" class="btn btn-sm btn-judicial-outline">
                <i class="bi bi-columns-gap me-1"></i>Compare
              </a>
            </div>

            <div class="d-flex align-items-center gap-2">
              <button type="button" class="btn btn-sm btn-judicial-outline copy-citation-btn" data-citation="${LG.utils.escapeHtml(citationText)}" title="Copy Standard Citation">
                <i class="bi bi-quote me-1"></i>Copy Citation
              </button>
              <button type="button" class="btn btn-sm btn-judicial-outline bookmark-btn" data-id="${encodeURIComponent(item.id)}" title="Save to Research Bookmarks">
                <i class="bi bi-bookmark text-danger"></i>
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');

    $resultsContainer.html(html);

    // Attach Action Handlers
    $('.copy-citation-btn').on('click', function () {
      const citation = $(this).data('citation');
      LG.utils.copyToClipboard(citation, 'Citation copied: ' + citation);
    });

    $('.bookmark-btn').on('click', function () {
      if (!LG.session.isAuthenticated()) {
        LG.toast('Please sign in to save research bookmarks.', 'warning');
        return;
      }
      const caseId = $(this).data('id');
      const $btn = $(this);
      LG.api.bookmarks.add(caseId, 'Saved from Hybrid Search')
        .done(function () {
          LG.toast('Case saved to bookmarks!', 'success');
          $btn.html('<i class="bi bi-bookmark-fill text-warning"></i>');
        })
        .fail(function () {
          LG.toast('Case is already bookmarked or error occurred.', 'info');
        });
    });
  }

  /**
   * Render Pagination links.
   */
  function renderPagination(total, page) {
    const totalPages = Math.ceil(total / pageSize);
    if (totalPages <= 1) {
      $paginationNav.addClass('d-none');
      return;
    }

    $paginationNav.removeClass('d-none');
    let paginationHtml = '';

    // Previous Button
    paginationHtml += `
      <li class="page-item ${page === 1 ? 'disabled' : ''}">
        <a class="page-link bg-dark text-light border-secondary border-opacity-25" href="#" data-page="${page - 1}">Previous</a>
      </li>
    `;

    // Pages numbers
    const startPage = Math.max(1, page - 2);
    const endPage = Math.min(totalPages, page + 2);

    for (let p = startPage; p <= endPage; p++) {
      paginationHtml += `
        <li class="page-item ${p === page ? 'active' : ''}">
          <a class="page-link ${p === page ? 'bg-warning text-dark border-warning fw-bold' : 'bg-dark text-light border-secondary border-opacity-25'}" href="#" data-page="${p}">${p}</a>
        </li>
      `;
    }

    // Next Button
    paginationHtml += `
      <li class="page-item ${page === totalPages ? 'disabled' : ''}">
        <a class="page-link bg-dark text-light border-secondary border-opacity-25" href="#" data-page="${page + 1}">Next</a>
      </li>
    `;

    $paginationList.html(paginationHtml);

    $paginationList.find('a.page-link').on('click', function (e) {
      e.preventDefault();
      const targetPage = parseInt($(this).data('page'), 10);
      if (!isNaN(targetPage) && targetPage >= 1 && targetPage <= totalPages && targetPage !== currentPage) {
        executeSearch(targetPage);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });
  }

  // Load live verified repository stats
  LG.api.cases.getStats()
    .done(function (stats) {
      if (stats && stats.total_cases) {
        $('#total-cases-badge').text(`${stats.total_cases} Verified Court Judgments`);
      }
    });

  // Handle Form Submission
  $form.on('submit', function (e) {
    e.preventDefault();
    clearTimeout(debounceTimer);
    currentQuery = $input.val().trim();
    executeSearch(1);
  });

  // Debounced input search (250ms)
  $input.on('input', function () {
    clearTimeout(debounceTimer);
    const val = $input.val().trim();
    debounceTimer = setTimeout(function () {
      if (val !== currentQuery) {
        currentQuery = val;
        executeSearch(1);
      }
    }, 250);
  });

  // Query Suggestion Chips
  $('.query-chip').on('click', function () {
    const q = $(this).data('query');
    $input.val(q);
    currentQuery = q;
    executeSearch(1);
  });

  // Filter Buttons
  $applyFiltersBtn.on('click', function () {
    executeSearch(1);
  });

  $resetFiltersBtn.on('click', function () {
    $filterCourt.val('');
    $filterYearFrom.val('');
    $filterYearTo.val('');
    $filterAct.val('');
    $filterOutcome.val('');
    $('#filter-domain').val('');
    $('#filter-casetype').val('');
    executeSearch(1);
  });

  // Check URL query param on initial load
  const initialQ = LG.utils.getQueryParam('q');
  if (initialQ) {
    $input.val(initialQ);
    currentQuery = initialQ;
    executeSearch(1);
  } else {
    // Default initial load: search with empty query to show latest published judgments
    executeSearch(1);
  }
});
