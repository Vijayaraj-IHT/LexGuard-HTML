/**
 * LexGuard — Dedicated Split-Screen Staff Case Review Workstation (case-review.js)
 * Semester 5 Project · LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  // 1. RBAC Guard: Court Staff only
  if (!LG.requireAuth(['staff', 'court_staff', 'senior_staff'])) {
    return;
  }

  const caseId = LG.utils.getQueryParam('id');
  if (!caseId) {
    LG.toast('No case identifier specified. Redirecting to admin queue...', 'warning');
    setTimeout(function () { window.location.href = 'admin.html'; }, 1000);
    return;
  }

  // PDF.js worker setup
  if (window.pdfjsLib) {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
  }

  let currentCase = null;
  let pdfDoc = null;
  let pageNum = 1;
  let pageRendering = false;
  let pageNumPending = null;
  let scale = 1.15;
  let rotation = 0;

  // Header & Form Elements
  const $headerTitle = $('#review-header-title');
  const $hashBadge = $('#meta-hash-badge');
  const $editTitle = $('#edit-title');
  const $editCaseno = $('#edit-caseno');
  const $editCnr = $('#edit-cnr');
  const $editCourt = $('#edit-court');
  const $editYear = $('#edit-year');
  const $editBenchtype = $('#edit-benchtype');
  const $editJudge = $('#edit-judge');
  const $editDisposition = $('#edit-disposition');
  const $editPrecstatus = $('#edit-precstatus');
  const $editActs = $('#edit-acts');
  const $editRatio = $('#edit-ratio');
  const $editSummary = $('#edit-summary');

  // Action Buttons
  const $btnReextract = $('#btn-reextract');
  const $btnSaveMeta = $('#btn-save-meta');
  const $btnApproveSeal = $('#btn-approve-seal');
  const $btnRejectCase = $('#btn-reject-case');
  const $approveModal = new bootstrap.Modal(document.getElementById('approveSealModal'));
  const $confirmApproveBtn = $('#confirm-approve-btn');
  const $approveNote = $('#approve-note');

  // PDF Elements
  const $pdfLoading = $('#pdf-loading');
  const $pdfCanvas = $('#pdf-canvas');
  const $pdfFallbackText = $('#pdf-fallback-text');
  const $pdfCurrentPage = $('#pdf-current-page');
  const $pdfTotalPages = $('#pdf-total-pages');

  /**
   * Load Case Metadata and initialize form.
   */
  function loadCase() {
    LG.api.cases.get(caseId)
      .done(function (c) {
        currentCase = c;
        $headerTitle.text('Review: ' + (c.title || 'Judgment'));
        $hashBadge.text('SHA-256: ' + LG.utils.truncateHash(c.file_hash, 6));

        $editTitle.val(c.title || '');
        $editCaseno.val(c.case_no || '');
        $editCnr.val(c.cnr || '');
        if (c.court) $editCourt.val(c.court);
        $editYear.val(c.year || 2026);
        if (c.bench_type) $editBenchtype.val(c.bench_type);
        $editJudge.val(c.judge || '');
        if (c.disposition || c.outcome) $editDisposition.val(c.disposition || c.outcome);
        if (c.precedential_status) $editPrecstatus.val(c.precedential_status);

        const allTags = (c.act_tags || []).concat(c.section_tags || []);
        $editActs.val(allTags.join(', '));
        $editRatio.val(c.ratio_decidendi || '');
        $editSummary.val(c.summary || '');

        loadPdf();
      })
      .fail(function (xhr) {
        const is404 = xhr.status === 404;
        const safeId = LG.utils.escapeHtml(caseId || 'Unknown');
        $('main.lg-main .container-fluid').html(`
          <div class="card card-judicial text-center p-5 my-4 shadow-lg border-secondary border-opacity-30">
            <div class="d-inline-flex align-items-center justify-content-center mb-3 mx-auto" style="width: 72px; height: 72px; border-radius: 20px; background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35);">
              <i class="bi bi-file-earmark-x fs-1 text-warning"></i>
            </div>
            <div class="badge bg-warning text-dark px-3 py-1 mb-2 fw-semibold mx-auto" style="width: fit-content;">HTTP 404 · DOCKET NOT FOUND</div>
            <h2 class="h3 font-serif fw-bold text-light mb-2">Case Ingestion Record Not Found</h2>
            <p class="text-secondary max-w-lg mx-auto mb-4">
              No pending or registered case record found matching identifier <code class="text-warning font-monospace">${safeId}</code>. It may have already been sealed, transferred, or rejected.
            </p>
            <div class="d-flex justify-content-center gap-3">
              <a href="admin.html?auth_role=staff" class="btn btn-gold"><i class="bi bi-speedometer2 me-1"></i>Return to Staff Workstation</a>
              <a href="case-upload.html" class="btn btn-judicial-outline"><i class="bi bi-cloud-arrow-up me-1"></i>Upload New PDF</a>
            </div>
          </div>
        `);
        LG.toast(is404 ? 'Docket not found for review (HTTP 404).' : 'Failed to load case record.', 'warning');
      });
  }

  /**
   * Load PDF into left pane.
   */
  function loadPdf() {
    const pdfUrl = LG.api.cases.getOfficialContentUrl(caseId);

    if (window.pdfjsLib) {
      window.pdfjsLib.getDocument({
        url: pdfUrl,
        withCredentials: true
      }).promise.then(function (loadedDoc) {
        pdfDoc = loadedDoc;
        $pdfTotalPages.text(pdfDoc.numPages);
        $pdfLoading.addClass('d-none');
        $pdfCanvas.removeClass('d-none');
        renderPdfPage(pageNum);
      }).catch(function (err) {
        console.warn('PDF stream failed in review:', err);
        $pdfLoading.addClass('d-none');
        if (currentCase && (currentCase.raw_text || currentCase.summary)) {
          $pdfFallbackText.removeClass('d-none').text(currentCase.raw_text || currentCase.summary);
        }
      });
    }
  }

  function renderPdfPage(num) {
    pageRendering = true;
    pdfDoc.getPage(num).then(function (page) {
      const canvas = document.getElementById('pdf-canvas');
      const ctx = canvas.getContext('2d');
      const viewport = page.getViewport({ scale: scale, rotation: rotation });
      canvas.height = viewport.height;
      canvas.width = viewport.width;

      const renderTask = page.render({ canvasContext: ctx, viewport: viewport });
      renderTask.promise.then(function () {
        pageRendering = false;
        if (pageNumPending !== null) {
          renderPdfPage(pageNumPending);
          pageNumPending = null;
        }
      });
    });

    $pdfCurrentPage.text(num);
  }

  function queuePdfPage(num) {
    if (pageRendering) {
      pageNumPending = num;
    } else {
      renderPdfPage(num);
    }
  }

  $('#pdf-prev-page').on('click', function () {
    if (pageNum <= 1) return;
    pageNum--;
    queuePdfPage(pageNum);
  });

  $('#pdf-next-page').on('click', function () {
    if (!pdfDoc || pageNum >= pdfDoc.numPages) return;
    pageNum++;
    queuePdfPage(pageNum);
  });

  $('#pdf-zoom-in').on('click', function () {
    scale += 0.2;
    if (pdfDoc) queuePdfPage(pageNum);
  });

  $('#pdf-zoom-out').on('click', function () {
    if (scale <= 0.6) return;
    scale -= 0.2;
    if (pdfDoc) queuePdfPage(pageNum);
  });

  $('#pdf-rotate').on('click', function () {
    rotation = (rotation + 90) % 360;
    if (pdfDoc) queuePdfPage(pageNum);
  });

  /**
   * Action 1: Re-extract CIS with NLP.
   */
  $btnReextract.on('click', function () {
    $btnReextract.prop('disabled', true).html('<span class="spinner-border spinner-border-sm me-1"></span>Running NLP...');

    LG.api.cases.reExtract(caseId)
      .done(function (res) {
        LG.toast('NLP CIS re-extraction complete!', 'success');
        loadCase();
      })
      .fail(function () {
        LG.toast('Failed to re-extract CIS metadata.', 'danger');
      })
      .always(function () {
        $btnReextract.prop('disabled', false).html('<i class="bi bi-arrow-repeat me-1"></i>Re-extract NLP');
      });
  });

  /**
   * Action 2: Save Metadata Edits (PATCH /cases/{caseId}).
   */
  $btnSaveMeta.on('click', function () {
    $btnSaveMeta.prop('disabled', true).html('<span class="spinner-border spinner-border-sm me-1"></span>Saving...');

    const actsList = $editActs.val().split(',').map(s => s.trim()).filter(Boolean);

    const updatePayload = {
      title: $editTitle.val().trim(),
      case_no: $editCaseno.val().trim(),
      cnr: $editCnr.val().trim(),
      court: $editCourt.val(),
      year: parseInt($editYear.val(), 10),
      judge: $editJudge.val().trim(),
      disposition: $editDisposition.val(),
      precedential_status: $editPrecstatus.val(),
      act_tags: actsList,
      section_tags: actsList,
      ratio_decidendi: $editRatio.val().trim(),
      summary: $editSummary.val().trim()
    };

    LG.api.request({
      url: '/cases/' + encodeURIComponent(caseId),
      method: 'PATCH',
      data: updatePayload
    })
      .done(function () {
        LG.toast('Metadata modifications saved successfully.', 'success');
      })
      .fail(function () {
        LG.toast('Failed to save metadata modifications.', 'danger');
      })
      .always(function () {
        $btnSaveMeta.prop('disabled', false).html('<i class="bi bi-save me-1"></i>Save Edits');
      });
  });

  /**
   * Action 3: Approve & Seal (Phi_case).
   */
  $btnApproveSeal.on('click', function () {
    $approveModal.show();
  });

  $confirmApproveBtn.on('click', function () {
    const note = $approveNote.val().trim() || 'Verified against certified record by Court Staff.';

    LG.api.admin.approve(caseId, note)
      .done(function () {
        LG.toast('Composite judicial seal affixed! Judgment published.', 'success');
        $approveModal.hide();
        setTimeout(function () {
          window.location.href = 'admin.html';
        }, 1200);
      })
      .fail(function () {
        LG.toast('Failed to approve and seal case.', 'danger');
      });
  });

  /**
   * Action 4: Reject Submission.
   */
  $btnRejectCase.on('click', function () {
    if (!confirm('Are you sure you want to reject this case submission?')) return;

    LG.api.request({
      url: '/admin/approve/' + encodeURIComponent(caseId),
      method: 'POST',
      data: {
        status: 'rejected',
        review_note: 'Rejected during human-in-the-loop audit.'
      }
    })
      .done(function () {
        LG.toast('Case submission rejected.', 'warning');
        setTimeout(function () {
          window.location.href = 'admin.html';
        }, 1000);
      })
      .fail(function () {
        LG.toast('Failed to reject case.', 'danger');
      });
  });

  /* -------------------------------------------------------------------------
     Draggable Resizer Divider Logic
     ------------------------------------------------------------------------- */
  const $resizer = $('#resizer-gutter');
  const $leftPane = $('#left-pane');
  const $rightPane = $('#right-pane');
  const $splitWrap = $('#review-split-container');
  let isDragging = false;

  $resizer.on('mousedown', function (e) {
    e.preventDefault();
    isDragging = true;
    $resizer.addClass('dragging');
    $('body').css('user-select', 'none').css('cursor', 'col-resize');
  });

  $(document).on('mousemove', function (e) {
    if (!isDragging) return;
    const containerOffset = $splitWrap.offset().left;
    const containerWidth = $splitWrap.width();
    const pointerX = e.pageX - containerOffset;

    let leftPercent = (pointerX / containerWidth) * 100;
    if (leftPercent < 25) leftPercent = 25;
    if (leftPercent > 75) leftPercent = 75;

    $leftPane.css('flex', `1 1 ${leftPercent}%`);
    $rightPane.css('flex', `1 1 ${100 - leftPercent}%`);
  });

  $(document).on('mouseup', function () {
    if (isDragging) {
      isDragging = false;
      $resizer.removeClass('dragging');
      $('body').css('user-select', '').css('cursor', '');
    }
  });

  // Initial Load
  loadCase();
});
