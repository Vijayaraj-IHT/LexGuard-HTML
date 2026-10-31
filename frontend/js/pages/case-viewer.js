/**
 * LexGuard — 4-Tab Case Viewer & PDF.js Engine (case-viewer.js)
 * LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  const caseId = LG.utils.getQueryParam('id');
  if (!caseId) {
    LG.toast('No case identifier provided. Redirecting to search...', 'warning');
    setTimeout(function () { window.location.href = 'search.html'; }, 1000);
    return;
  }

  // Setup PDF.js worker
  if (window.pdfjsLib) {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
  }

  let pdfDoc = null;
  let pageNum = 1;
  let pageRendering = false;
  let pageNumPending = null;
  let scale = 1.25;
  let rotation = 0;
  let currentCase = null;

  // DOM Elements
  const $headerTitle = $('#case-header-title');
  const $headerCourt = $('#case-header-court');
  const $headerCaseno = $('#case-header-caseno');
  const $headerDate = $('#case-header-date');
  const $headerBench = $('#case-header-bench');
  const $headerCnr = $('#case-header-cnr');
  const $headerOutcome = $('#case-header-outcome');
  const $sealHash = $('#case-seal-hash');
  const $verifyLink = $('#case-verify-link');
  const $downloadBtn = $('#action-download-btn');
  const $compareBtn = $('#action-compare-btn');
  const $bookmarkBtn = $('#action-bookmark-btn');

  // Overview Tab Elements
  const $ratio = $('#overview-ratio');
  const $summary = $('#overview-summary');
  const $issues = $('#overview-issues');
  const $metaCourt = $('#meta-court');
  const $metaCasetype = $('#meta-casetype');
  const $metaYear = $('#meta-year');
  const $metaOutcome = $('#meta-outcome');
  const $metaStatus = $('#meta-status');
  const $overviewTags = $('#overview-tags');
  const $citationBox = $('#overview-citation-box');
  const $copyCitationBtn = $('#overview-copy-citation-btn');

  // PDF Viewer Elements
  const $pdfLoading = $('#pdf-loading');
  const $pdfCanvas = $('#pdf-canvas');
  const $pdfFallbackText = $('#pdf-fallback-text');
  const $pdfCurrentPage = $('#pdf-current-page');
  const $pdfTotalPages = $('#pdf-total-pages');
  const $pdfZoomLevel = $('#pdf-zoom-level');

  /**
   * Fetch and render case details.
   */
  LG.api.cases.get(caseId)
    .done(function (c) {
      currentCase = c;
      renderCaseHeader(c);
      renderOverviewTab(c);
      renderCisTab(c);
      loadPrecedentNetwork(c.id);

      // Setup action buttons
      $downloadBtn.attr('href', LG.api.cases.getDownloadUrl(c.id));
      $compareBtn.attr('href', 'case-compare.html?case1=' + encodeURIComponent(c.id));
      $verifyLink.attr('href', 'verify.html?hash=' + encodeURIComponent(c.file_hash || ''));
    })
    .fail(function (xhr) {
      const is404 = xhr.status === 404;
      let msg = 'Could not load judgment metadata.';
      if (xhr.responseJSON && xhr.responseJSON.detail) {
        msg = typeof xhr.responseJSON.detail === 'string'
          ? xhr.responseJSON.detail
          : JSON.stringify(xhr.responseJSON.detail);
      }
      
      const safeId = LG.utils.escapeHtml(caseId || 'Unknown');
      $('main.lg-main .container-fluid').html(`
        <div class="card card-judicial text-center p-5 my-4 shadow-lg border-secondary border-opacity-30">
          <div class="d-inline-flex align-items-center justify-content-center mb-3 mx-auto" style="width: 72px; height: 72px; border-radius: 20px; background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35);">
            <i class="bi bi-file-earmark-x fs-1 text-warning"></i>
          </div>
          <div class="badge bg-warning text-dark px-3 py-1 mb-2 fw-semibold mx-auto" style="width: fit-content;">HTTP 404 · RECORD NOT FOUND</div>
          <h2 class="h3 font-serif fw-bold text-light mb-2">Judicial Record Not Found</h2>
          <p class="text-secondary max-w-lg mx-auto mb-4">
            The requested judicial precedent docket (<code class="text-warning font-monospace">${safeId}</code>) could not be located in the repository. ${LG.utils.escapeHtml(msg)}
          </p>
          <div class="d-flex justify-content-center flex-wrap gap-3">
            <a href="search.html" class="btn btn-gold"><i class="bi bi-search me-1"></i>Return to Precedent Search</a>
            <a href="acts-explorer.html" class="btn btn-judicial-outline"><i class="bi bi-book-half me-1"></i>Statutory Explorer</a>
            <a href="admin.html?auth_role=staff" class="btn btn-judicial-outline"><i class="bi bi-speedometer2 me-1"></i>Staff Workstation</a>
          </div>
        </div>
      `);
      LG.toast(is404 ? 'Case record not found (HTTP 404).' : msg, 'warning');
    });

  /**
   * Safe in-text statute linkifier.
   * Transforms statutory section references into interactive clickable links to Acts Explorer.
   */
  function linkifyLegalText(text) {
    if (!text) return '';
    const escaped = LG.utils.escapeHtml(text);
    
    // Pattern: Section 482 of CrPC, Sec. 138 NI Act, Article 226 of the Constitution
    const pattern = /\b(Section|Sec\.|Article|Art\.)\s+(\d+[A-Z]?(\s*\([0-9a-zA-Z]+\))*)\s*(?:of\s+(?:the\s+)?)?([A-Za-z\s,\.]{2,35}?(?:Act|Code|Constitution|Rules|Order|Cr\.?P\.?C\.?|I\.?P\.?C\.?|N\.?I\.?\s*Act|N\.?D\.?P\.?S\.?|P\.?O\.?C\.?S\.?O\.?|P\.?M\.?L\.?A\.?))\b/gi;
    
    return escaped.replace(pattern, function(match, prefix, secNo, subP, actName) {
      let actCode = 'CRPC';
      const aUpper = (actName || '').toUpperCase();
      if (aUpper.includes('CRPC') || aUpper.includes('CRIMINAL')) actCode = 'CRPC';
      else if (aUpper.includes('IPC') || aUpper.includes('PENAL')) actCode = 'IPC';
      else if (aUpper.includes('CONST')) actCode = 'CONST';
      else if (aUpper.includes('NI') || aUpper.includes('NEGOTIABLE')) actCode = 'NI_ACT';
      else if (aUpper.includes('NDPS') || aUpper.includes('NARCOTIC')) actCode = 'NDPS';
      else if (aUpper.includes('POCSO')) actCode = 'POCSO';
      else if (aUpper.includes('PMLA') || aUpper.includes('LAUNDERING')) actCode = 'PMLA';
      else if (aUpper.includes('ARBITRATION')) actCode = 'ARB';
      else if (aUpper.includes('SPECIFIC RELIEF')) actCode = 'SRA';
      else if (aUpper.includes('CIVIL PROCEDURE') || aUpper.includes('CPC')) actCode = 'CPC';
      else if (aUpper.includes('CORRUPTION')) actCode = 'PCA';
      else if (aUpper.includes('EVIDENCE')) actCode = 'IEA';
      
      const cleanSec = secNo.trim().split(' ')[0];
      return `<a href="acts-explorer.html?act=${encodeURIComponent(actCode)}&section=${encodeURIComponent(cleanSec)}" class="badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25 px-1 py-0.5 rounded text-decoration-none fw-semibold" style="font-size: 0.85em;" title="Explore ${actName} Section ${cleanSec} in Acts Explorer"><i class="bi bi-book me-1"></i>${match}</a>`;
    });
  }

  /**
   * Render Case Header & Identification details.
   */
  function renderCaseHeader(c) {
    $headerTitle.text(c.title || 'Untitled Case');
    $headerCourt.attr('class', LG.utils.courtBadgeClass(c.court)).text(c.court || 'Court');
    $headerCaseno.html(`<i class="bi bi-file-earmark-text me-1"></i>Case No: <span class="text-light">${LG.utils.escapeHtml(c.case_no || '—')}</span>`);
    $headerDate.html(`<i class="bi bi-calendar3 me-1"></i>Date: <span class="text-light">${LG.utils.formatDate(c.decision_date || c.created_at)}</span>`);
    $headerBench.html(`<i class="bi bi-person-badge me-1"></i>Bench: <span class="text-light">${LG.utils.escapeHtml(c.judge || 'Hon\'ble Bench')}</span>`);
    $headerCnr.html(`<i class="bi bi-upc-scan me-1"></i>CNR: <span class="text-light font-mono">${LG.utils.escapeHtml(c.cnr_number || c.cnr || '—')}</span>`);

    if (c.outcome) {
      $headerOutcome.text(c.outcome).show();
    } else {
      $headerOutcome.hide();
    }

    if (c.file_hash) {
      $sealHash.text('SHA-256: ' + c.file_hash);
    } else {
      $sealHash.text('SHA-256 Digest Pending');
    }
  }

  /**
   * Render Tab 1: Structure & Overview.
   */
  function renderOverviewTab(c) {
    $ratio.html(linkifyLegalText(c.ratio_decidendi || 'Legal principles and ratio decidendi affirmed under judicial consideration.'));
    $summary.html(linkifyLegalText(c.summary || 'Summary under extraction from official court records.'));
    $issues.html(linkifyLegalText(c.issues_framed || '1. Statutory compliance with procedural standards.\n2. Fundamental rights invocation and constitutional remedy validity.'));

    // Populate Citizen View Card
    const layman = c.layman_summary || `In this ${c.case_type || 'case'}, the Court examined the dispute involving ${c.title || 'the parties'}. The ruling resulted in the petition being ${c.outcome || c.disposition || 'disposed'}.`;
    $('#citizen-summary-text').text(layman);
    $('#citizen-takeaway').html(`<strong>Final Judicial Outcome:</strong> <span class="badge badge-gold">${LG.utils.escapeHtml(c.outcome || c.disposition || 'Disposed')}</span> under <strong>${LG.utils.escapeHtml(c.court || 'Court')}</strong>.`);

    $metaCourt.text(c.court || '—');
    $metaCasetype.text(c.case_type || c.cis_case_type || 'Civil / Criminal');
    $metaYear.text(c.year || '—');
    $metaOutcome.text(c.outcome || c.disposition || 'Disposed');
    $metaStatus.html(`<span class="${LG.utils.statusBadgeClass(c.verification_status || c.status)}">${c.verification_status || c.status || 'Verified'}</span>`);

    // Tags
    const acts = c.acts || c.act_tags || [];
    const sections = c.sections || c.section_tags || [];
    const kws = c.keyword_tags || [];
    const all = acts.concat(sections);
    if (all.length > 0) {
      $overviewTags.html(all.map(t => `<span class="badge bg-light text-danger border border-danger border-opacity-25">${LG.utils.escapeHtml(t)}</span>`).join(' '));
    }

    // Populate Keyword Entity Chips for in-document search
    const allChips = acts.concat(sections).concat(kws);
    const $chipsContainer = $('#keyword-entity-chips');
    $chipsContainer.empty();
    if (allChips.length > 0) {
      allChips.slice(0, 10).forEach(function (tag) {
        const chip = $(`<button type="button" class="btn btn-xs btn-outline-danger py-0 px-2 rounded-pill" style="font-size: 0.72rem; font-weight: 600; background: #ffffff;">${LG.utils.escapeHtml(tag)}</button>`);
        chip.on('click', function () {
          $('#doc-keyword-input').val(tag);
          executeDocKeywordSearch(tag);
        });
        $chipsContainer.append(chip);
      });
    } else {
      $chipsContainer.html('<span class="text-secondary small fst-italic">No legal entities extracted</span>');
    }

    // Citation
    const citation = c.official_citation || `${c.title || 'Case'}, (${c.year || ''}) ${c.court || ''}`;
    $citationBox.text(citation);

    $copyCitationBtn.on('click', function () {
      LG.utils.copyToClipboard(citation, 'Citation copied: ' + citation);
    });

    // Mode Toggle Event Listeners
    $('#mode-advocate').off('change').on('change', function () {
      if ($(this).is(':checked')) {
        $('#citizen-card').addClass('d-none');
        $ratio.closest('.card').removeClass('d-none');
        $issues.closest('.card').removeClass('d-none');
      }
    });

    $('#mode-citizen').off('change').on('change', function () {
      if ($(this).is(':checked')) {
        $('#citizen-card').removeClass('d-none');
        $ratio.closest('.card').addClass('d-none');
        $issues.closest('.card').addClass('d-none');
      }
    });
  }

  /* -------------------------------------------------------------------------
     In-Document Keyword Search & Extraction Engine
     ------------------------------------------------------------------------- */
  function executeDocKeywordSearch(query) {
    query = (query || $('#doc-keyword-input').val() || '').trim();
    if (!query) {
      $('#doc-keyword-results-panel').addClass('d-none');
      $('#doc-keyword-clear-btn').addClass('d-none');
      return;
    }

    $('#doc-keyword-clear-btn').removeClass('d-none');
    $('#doc-keyword-btn-spinner').removeClass('d-none');
    $('#doc-keyword-submit-btn').prop('disabled', true);

    LG.api.cases.searchKeywords(caseId, query)
      .done(function (res) {
        const matches = res.total_matches || 0;
        const pages = res.pages_matched || [];
        const occurrences = res.occurrences || [];

        $('#doc-keyword-match-count').text(`${matches} match${matches !== 1 ? 'es' : ''} found`);
        $('#doc-keyword-pages-summary').text(`across ${pages.length} page${pages.length !== 1 ? 's' : ''}`);

        // Render Page Pills
        const $pills = $('#doc-keyword-page-pills');
        $pills.empty();
        pages.forEach(function (p) {
          const pill = $(`<button type="button" class="btn btn-xs btn-outline-warning px-2 py-1"><i class="bi bi-file-earmark-text me-1"></i>Page ${p}</button>`);
          pill.on('click', function () {
            // Switch to PDF tab
            const tabTrigger = new bootstrap.Tab(document.getElementById('tab-pdf-btn'));
            tabTrigger.show();
            // Jump to page
            pageNum = p;
            queueRenderPage(pageNum);
            $pdfCurrentPage.val(p);
          });
          $pills.append(pill);
        });

        // Render Context Snippets
        const $snippets = $('#doc-keyword-snippets-container');
        $snippets.empty();
        if (occurrences.length > 0) {
          occurrences.forEach(function (occ) {
            const card = $(`
              <div class="card bg-dark border-secondary border-opacity-25 p-2 small">
                <div class="d-flex align-items-center justify-content-between mb-1">
                  <span class="badge bg-secondary font-mono" style="font-size: 0.68rem;">Page ${occ.page} · Line ${occ.line_no}</span>
                  <button type="button" class="btn btn-xs btn-link text-warning p-0 text-decoration-none">Jump to Page ${occ.page} &rarr;</button>
                </div>
                <div class="text-light font-monospace small">${occ.snippet || occ.raw_text}</div>
              </div>
            `);
            card.find('button').on('click', function () {
              const tabTrigger = new bootstrap.Tab(document.getElementById('tab-pdf-btn'));
              tabTrigger.show();
              pageNum = occ.page;
              queueRenderPage(pageNum);
              $pdfCurrentPage.val(occ.page);
            });
            $snippets.append(card);
          });
        } else {
          $snippets.html('<div class="text-secondary small fst-italic">No contextual snippets available.</div>');
        }

        $('#doc-keyword-results-panel').removeClass('d-none');
      })
      .fail(function (xhr) {
        LG.toast('Keyword search error or no matches found.', 'warning');
      })
      .always(function () {
        $('#doc-keyword-btn-spinner').addClass('d-none');
        $('#doc-keyword-submit-btn').prop('disabled', false);
      });
  }

  $('#doc-keyword-search-form').on('submit', function (e) {
    e.preventDefault();
    executeDocKeywordSearch();
  });

  // Replaces the former inline onclick on the certificate print button.
  $('#cert-print-btn').on('click', function () {
    window.print();
  });

  $('#doc-keyword-clear-btn').on('click', function () {
    $('#doc-keyword-input').val('');
    $('#doc-keyword-results-panel').addClass('d-none');
    $(this).addClass('d-none');
  });

  /**
   * Render Tab 3: CIS Metadata fields and JSON viewer.
   */
  function renderCisTab(c) {
    $('#cis-cnr').text(c.cnr_number || c.cnr || '—');
    $('#cis-casetype').text(c.cis_case_type || c.case_type || 'Writ Petition / Appeal');
    $('#cis-regno').text(c.case_no || '—');
    $('#cis-filingdate').text(LG.utils.formatDate(c.filing_date || c.created_at));
    $('#cis-decisiondate').text(LG.utils.formatDate(c.decision_date || c.created_at));
    $('#cis-petitioner').text(c.petitioner || 'Petitioner Counsel');
    $('#cis-respondent').text(c.respondent || 'Respondent / State');
    $('#cis-coram').text(c.judge || 'Hon\'ble Judges of the Bench');
    $('#cis-fir').text(c.fir_number || 'N/A');
    $('#cis-lowercourt').text(c.lower_court || 'N/A');

    // JSON pretty print
    $('#cis-raw-json').text(JSON.stringify(c, null, 2));
  }

  /**
   * Render Tab 4: Precedents & Citator Graph.
   */
  function loadPrecedentNetwork(cid) {
    LG.api.comparison.getPrecedents(cid)
      .done(function (res) {
        const list = res.precedents || res.results || res;
        if (!Array.isArray(list) || list.length === 0) {
          $('#precedents-list').html(`
            <div class="text-secondary small p-3 text-center border border-secondary border-opacity-15 rounded">
              <i class="bi bi-info-circle me-1"></i>No upstream or downstream precedent citations indexed for this case yet.
            </div>
          `);
          return;
        }

        const itemsHtml = list.map(function (p) {
          return `
            <div class="card card-judicial p-3 mb-2">
              <div class="d-flex align-items-center justify-content-between">
                <div>
                  <a href="case-viewer.html?id=${encodeURIComponent(p.id)}" class="fw-semibold text-light text-decoration-none">
                    ${LG.utils.escapeHtml(p.title || 'Precedent')}
                  </a>
                  <div class="small text-secondary mt-1">
                    <span class="${LG.utils.courtBadgeClass(p.court)} me-2">${LG.utils.escapeHtml(p.court || '')}</span>
                    <span>Year: ${p.year || '—'}</span>
                  </div>
                </div>
                <div>
                  <a href="case-compare.html?case1=${encodeURIComponent(cid)}&case2=${encodeURIComponent(p.id)}" class="btn btn-xs btn-judicial-outline">
                    <i class="bi bi-columns-gap me-1"></i>Compare
                  </a>
                </div>
              </div>
            </div>
          `;
        }).join('');

        $('#precedents-list').html(itemsHtml);
      })
      .fail(function () {
        $('#precedents-list').html(`
          <div class="text-secondary small p-3 text-center">
            Precedent relationship analysis available in Comparator view.
          </div>
        `);
      });
  }

  /* -------------------------------------------------------------------------
     Advanced Mozilla PDF.js Engine: Selectable TextLayer, Thumbnails & Search
     ------------------------------------------------------------------------- */
  const $canvasWrapper = $('#canvas-wrapper');
  const $textLayer = $('#pdf-text-layer');
  const $thumbnailsDrawer = $('#pdf-thumbnails-drawer');
  const $thumbnailsList = $('#thumbnails-list');
  const $matchCounter = $('#pdf-match-counter');
  const $searchPrevBtn = $('#pdf-search-prev');
  const $searchNextBtn = $('#pdf-search-next');
  const $searchInput = $('#pdf-search-input');
  const $fullscreenBtn = $('#pdf-fullscreen-btn');
  const $fullscreenIcon = $('#pdf-fullscreen-icon');
  const $printBtn = $('#pdf-print-btn');
  const $toggleThumbnailsBtn = $('#pdf-toggle-thumbnails');

  // Search matches state
  let searchMatches = []; // array of { pageNum, text }
  let currentMatchIdx = -1;

  function renderPage(num) {
    pageRendering = true;
    pdfDoc.getPage(num).then(function (page) {
      const canvas = document.getElementById('pdf-canvas');
      const ctx = canvas.getContext('2d');
      const viewport = page.getViewport({ scale: scale, rotation: rotation });

      canvas.height = viewport.height;
      canvas.width = viewport.width;

      // Position text layer exactly over the canvas
      $textLayer.css({
        width: viewport.width + 'px',
        height: viewport.height + 'px'
      }).empty();

      const renderContext = {
        canvasContext: ctx,
        viewport: viewport
      };

      const renderTask = page.render(renderContext);
      renderTask.promise.then(function () {
        pageRendering = false;

        // Render selectable text layer
        page.getTextContent().then(function (textContent) {
          const query = $searchInput.val().trim().toLowerCase();

          textContent.items.forEach(function (item) {
            const tx = pdfjsLib.Util.transform(viewport.transform, item.transform);
            const fontHeight = Math.sqrt((tx[2] * tx[2]) + (tx[3] * tx[3]));

            const span = document.createElement('span');
            let itemText = item.str;

            if (query && itemText.toLowerCase().includes(query)) {
              span.className = 'highlight';
            }

            span.textContent = itemText;
            span.style.left = (tx[4]) + 'px';
            span.style.top = (tx[5] - fontHeight) + 'px';
            span.style.fontSize = fontHeight + 'px';
            span.style.fontFamily = item.fontName || 'sans-serif';
            document.getElementById('pdf-text-layer').appendChild(span);
          });
        });

        // Highlight active thumbnail
        $('.lg-thumbnail-item').removeClass('active');
        $(`#thumb-page-${num}`).addClass('active');

        if (pageNumPending !== null) {
          renderPage(pageNumPending);
          pageNumPending = null;
        }
      });
    });

    $pdfCurrentPage.val(num);
  }

  function queueRenderPage(num) {
    if (pageRendering) {
      pageNumPending = num;
    } else {
      renderPage(num);
    }
  }

  function onPrevPage() {
    if (pageNum <= 1) return;
    pageNum--;
    queueRenderPage(pageNum);
  }

  function onNextPage() {
    if (!pdfDoc || pageNum >= pdfDoc.numPages) return;
    pageNum++;
    queueRenderPage(pageNum);
  }

  /**
   * Render thumbnail canvas previews in sidebar drawer.
   */
  function renderThumbnails() {
    $thumbnailsList.empty();
    if (!pdfDoc) return;

    for (let i = 1; i <= Math.min(pdfDoc.numPages, 30); i++) {
      const pageIndex = i;
      const thumbId = `thumb-page-${pageIndex}`;
      const thumbHtml = `
        <div class="lg-thumbnail-item ${pageIndex === pageNum ? 'active' : ''}" id="${thumbId}" data-page="${pageIndex}">
          <canvas id="thumb-canvas-${pageIndex}"></canvas>
          <div class="lg-thumbnail-label">Page ${pageIndex}</div>
        </div>
      `;
      $thumbnailsList.append(thumbHtml);

      // Render miniature page thumbnail
      pdfDoc.getPage(pageIndex).then(function (page) {
        const thumbCanvas = document.getElementById(`thumb-canvas-${pageIndex}`);
        if (!thumbCanvas) return;
        const ctx = thumbCanvas.getContext('2d');
        const viewport = page.getViewport({ scale: 0.22 });
        thumbCanvas.width = viewport.width;
        thumbCanvas.height = viewport.height;
        page.render({ canvasContext: ctx, viewport: viewport });
      });
    }

    // Click handler on thumbnail to jump to page
    $('.lg-thumbnail-item').on('click', function () {
      const targetPage = parseInt($(this).data('page'), 10);
      if (!isNaN(targetPage)) {
        pageNum = targetPage;
        queueRenderPage(pageNum);
      }
    });
  }

  /**
   * Search within entire PDF document.
   */
  function searchInPdf() {
    const q = $searchInput.val().trim().toLowerCase();
    searchMatches = [];
    currentMatchIdx = -1;

    if (!q || !pdfDoc) {
      $matchCounter.text('');
      $searchPrevBtn.prop('disabled', true);
      $searchNextBtn.prop('disabled', true);
      queueRenderPage(pageNum);
      return;
    }

    $matchCounter.text('Searching...');
    const searchPromises = [];

    for (let i = 1; i <= pdfDoc.numPages; i++) {
      searchPromises.push(
        pdfDoc.getPage(i).then(function (p) {
          return p.getTextContent().then(function (tc) {
            const pageText = tc.items.map(it => it.str).join(' ').toLowerCase();
            if (pageText.includes(q)) {
              return p.pageNumber;
            }
            return null;
          });
        })
      );
    }

    Promise.all(searchPromises).then(function (pagesWithMatches) {
      searchMatches = pagesWithMatches.filter(Boolean);

      if (searchMatches.length > 0) {
        currentMatchIdx = 0;
        $matchCounter.text(`Page ${searchMatches[0]} (1 of ${searchMatches.length})`);
        $searchPrevBtn.prop('disabled', false);
        $searchNextBtn.prop('disabled', false);
        pageNum = searchMatches[0];
        queueRenderPage(pageNum);
      } else {
        $matchCounter.text('0 matches');
        $searchPrevBtn.prop('disabled', true);
        $searchNextBtn.prop('disabled', true);
      }
    });
  }

  // Load PDF when PDF tab is clicked
  let pdfLoaded = false;
  $('#tab-pdf-btn').on('shown.bs.tab', function () {
    if (pdfLoaded) return;
    pdfLoaded = true;

    const downloadEndpoint = LG.config.API_BASE + '/cases/' + encodeURIComponent(caseId) + '/download';
    const token = LG.session.token();
    const headers = {};
    if (token) headers['Authorization'] = 'Bearer ' + token;

    if (window.pdfjsLib) {
      $pdfLoading.removeClass('d-none');
      $canvasWrapper.addClass('d-none');
      $pdfFallbackText.addClass('d-none');

      fetch(downloadEndpoint, {
        headers: headers,
        credentials: 'include'
      })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('PDF stream error: HTTP ' + response.status);
        }
        return response.arrayBuffer();
      })
      .then(function (buffer) {
        return window.pdfjsLib.getDocument({
          data: buffer,
          cMapUrl: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/cmaps/',
          cMapPacked: true
        }).promise;
      })
      .then(function (loadedDoc) {
        pdfDoc = loadedDoc;
        $pdfTotalPages.text(pdfDoc.numPages);
        $pdfLoading.addClass('d-none');
        $canvasWrapper.removeClass('d-none');
        renderPage(pageNum);
        renderThumbnails();
      })
      .catch(function (err) {
        console.warn('PDF.js binary render issue, falling back to text:', err);
        $pdfLoading.addClass('d-none');
        if (currentCase && (currentCase.full_text || currentCase.summary)) {
          $pdfFallbackText.removeClass('d-none').html(`
            <div class="p-4 bg-dark rounded border border-secondary border-opacity-25 font-monospace small" style="white-space: pre-wrap; line-height: 1.6;">
              ${LG.utils.escapeHtml(currentCase.full_text || currentCase.summary)}
            </div>
          `);
        } else {
          $pdfFallbackText.removeClass('d-none').html(`
            <div class="text-center py-4">
              <i class="bi bi-file-earmark-pdf fs-1 text-danger mb-2"></i>
              <p class="text-secondary small">Direct PDF rendering requires downloaded stream.</p>
              <a href="${LG.api.cases.getDownloadUrl(caseId)}" class="btn btn-sm btn-gold" target="_blank">
                <i class="bi bi-download me-1"></i>Download Official PDF
              </a>
            </div>
          `);
        }
      });
    }
  });

  // PDF Viewer Controls Handlers
  $('#pdf-prev-page').on('click', onPrevPage);
  $('#pdf-next-page').on('click', onNextPage);

  $pdfCurrentPage.on('change', function () {
    const val = parseInt($(this).val(), 10);
    if (!isNaN(val) && val >= 1 && pdfDoc && val <= pdfDoc.numPages) {
      pageNum = val;
      queueRenderPage(pageNum);
    }
  });

  $('#pdf-zoom-in').on('click', function () {
    scale += 0.25;
    $pdfZoomLevel.text(Math.round(scale * 100) + '%');
    if (pdfDoc) queueRenderPage(pageNum);
  });

  $('#pdf-zoom-out').on('click', function () {
    if (scale <= 0.5) return;
    scale -= 0.25;
    $pdfZoomLevel.text(Math.round(scale * 100) + '%');
    if (pdfDoc) queueRenderPage(pageNum);
  });

  $('#pdf-rotate').on('click', function () {
    rotation = (rotation + 90) % 360;
    if (pdfDoc) queueRenderPage(pageNum);
  });

  // Search Input Handler
  $searchInput.on('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      searchInPdf();
    }
  });

  $searchNextBtn.on('click', function () {
    if (searchMatches.length === 0) return;
    currentMatchIdx = (currentMatchIdx + 1) % searchMatches.length;
    pageNum = searchMatches[currentMatchIdx];
    $matchCounter.text(`Page ${pageNum} (${currentMatchIdx + 1} of ${searchMatches.length})`);
    queueRenderPage(pageNum);
  });

  $searchPrevBtn.on('click', function () {
    if (searchMatches.length === 0) return;
    currentMatchIdx = (currentMatchIdx - 1 + searchMatches.length) % searchMatches.length;
    pageNum = searchMatches[currentMatchIdx];
    $matchCounter.text(`Page ${pageNum} (${currentMatchIdx + 1} of ${searchMatches.length})`);
    queueRenderPage(pageNum);
  });

  // Fullscreen Mode Handler
  $fullscreenBtn.on('click', function () {
    const container = document.getElementById('pdf-main-container');
    if (!document.fullscreenElement) {
      if (container.requestFullscreen) {
        container.requestFullscreen();
      }
      $(container).addClass('fullscreen');
      $fullscreenIcon.attr('class', 'bi bi-fullscreen-exit');
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
      $(container).removeClass('fullscreen');
      $fullscreenIcon.attr('class', 'bi bi-fullscreen');
    }
  });

  // Print Button Handler
  $printBtn.on('click', function () {
    window.print();
  });

  // Toggle Thumbnails Drawer
  $toggleThumbnailsBtn.on('click', function () {
    $thumbnailsDrawer.toggleClass('collapsed');
  });

  // Case Brief Modal Handlers
  $('#action-case-brief-btn').on('click', function () {
    if (!currentCase) return;
    const c = currentCase;
    $('#brief-court-title').text((c.court || 'MADRAS HIGH COURT').toUpperCase());
    $('#brief-case-no').text(c.case_no || '—');
    $('#brief-cnr').text(c.cnr_number || c.cnr || '—');
    $('#brief-coram').text(c.judge || 'Hon\'ble Judges of the Bench');
    $('#brief-disposition').text(c.disposition || c.outcome || 'Disposed');
    $('#brief-parties').text(c.parties || (c.title ? c.title : 'Appellant v. Respondent'));
    
    const acts = c.acts || c.act_tags || [];
    const sections = c.sections || c.section_tags || [];
    const statutes = acts.concat(sections);
    if (statutes.length > 0) {
      $('#brief-statutes').html(statutes.map(s => `<span class="badge bg-secondary">${LG.utils.escapeHtml(s)}</span>`).join(' '));
    } else {
      $('#brief-statutes').text('General Criminal & Constitutional Principles');
    }

    $('#brief-ratio').text(c.ratio_decidendi || 'Ratio affirmed under binding authority.');
    $('#brief-summary').text(c.summary || c.facts || 'Case facts and procedural trajectory.');
    $('#brief-seal-hash').text('SHA-256: ' + (c.file_hash || 'Computed on record'));

    const modal = new bootstrap.Modal(document.getElementById('caseBriefModal'));
    modal.show();
  });

  $('#brief-copy-md-btn').on('click', function () {
    if (!currentCase) return;
    const c = currentCase;
    const md = `# JUDICIAL CASE BRIEF: ${c.case_no}\n\n**Court:** ${c.court}\n**CNR:** ${c.cnr_number || c.cnr || 'N/A'}\n**Coram:** ${c.judge}\n**Parties:** ${c.parties}\n**Disposition:** ${c.disposition || c.outcome}\n\n## Ratio Decidendi\n> ${c.ratio_decidendi}\n\n## Material Facts & Summary\n${c.summary || c.facts}\n\n---\n*LexGuard Verified SHA-256 Digest: ${c.file_hash}*`;
    LG.utils.copyToClipboard(md, 'Case brief markdown copied to clipboard!');
  });

  $('#brief-download-json-btn').on('click', function () {
    if (!currentCase) return;
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(currentCase, null, 2));
    const dlAnchor = document.createElement('a');
    dlAnchor.setAttribute('href', dataStr);
    dlAnchor.setAttribute('download', `case_brief_${currentCase.case_no.replace(/[^a-zA-Z0-9]/g, '_')}.json`);
    dlAnchor.click();
    dlAnchor.remove();
  });

  $('#brief-print-btn').on('click', function () {
    window.print();
  });

  // Bookmark Button Handler
  $bookmarkBtn.on('click', function () {
    if (!LG.session.isAuthenticated()) {
      LG.toast('Please sign in to save research bookmarks.', 'warning');
      return;
    }
    LG.api.bookmarks.add(caseId, 'Saved from Case Viewer')
      .done(function () {
        LG.toast('Case saved to your bookmarks!', 'success');
        $bookmarkBtn.find('i').attr('class', 'bi bi-bookmark-fill text-warning');
      })
      .fail(function () {
        LG.toast('Case is already in your bookmarks or error occurred.', 'info');
      });
  });
});
