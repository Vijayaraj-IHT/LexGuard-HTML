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
        if (xhr.statusText === 'abort' || xhr.status === 0) {
          return;
        }
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
  /**
   * Render the result list. Markup lives in LG.components.caseCard so the same
   * card can be reused by bookmarks and the comparison tray.
   */
  function renderResults(results) {
    if (!results || results.length === 0) {
      $resultsContainer.html('');
      return;
    }

    var card = LG.components && LG.components.caseCard;
    var html = results
      .map(function (item) {
        return card ? card.render(item) : '';
      })
      .join('');

    $resultsContainer.attr('aria-live', 'polite').html(html);

    // Delegated handlers: one binding for the whole list, not one per card.
    $resultsContainer
      .off('.casecard')
      .on('click.casecard', '.js-copy-citation', function () {
        var citation = $(this).attr('data-citation') || '';
        if (citation) LG.utils.copyToClipboard(citation, 'Citation copied');
      })
      .on('click.casecard', '.js-bookmark', function () {
        if (!LG.session.isAuthenticated()) {
          LG.toast('Please sign in to save research bookmarks.', 'warning');
          return;
        }
        var caseId = $(this).attr('data-id');
        var $btn = $(this);
        LG.api.bookmarks
          .add(caseId, 'Saved from Hybrid Search')
          .done(function () {
            LG.toast('Case saved to bookmarks!', 'success');
            $btn.attr('aria-pressed', 'true').html('<i class="bi bi-bookmark-fill text-warning"></i>');
          })
          .fail(function () {
            LG.toast('Case is already bookmarked or error occurred.', 'info');
          });
      });
  }

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
