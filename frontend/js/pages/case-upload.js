/**
 * LexGuard — Case Ingestion & Upload Controller (case-upload.js)
 * Semester 5 Project · LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  // 1. RBAC Check: Court Staff only
  if (!LG.requireAuth(['staff', 'court_staff', 'senior_staff'])) {
    return;
  }

  const $autoDropzone = $('#auto-dropzone');
  const $autoFileInput = $('#auto-file-input');
  const $autoBrowseBtn = $('#auto-browse-btn');
  const $autoFileLabel = $('#auto-file-label');
  const $autoSubmitBtn = $('#auto-submit-btn');
  const $autoProgress = $('#auto-upload-progress');
  const $autoForm = $('#auto-upload-form');

  const $manualForm = $('#manual-upload-form');
  const $manSubmitBtn = $('#man-submit-btn');

  const $successModal = new bootstrap.Modal(document.getElementById('uploadSuccessModal'));
  const $successCaseId = $('#success-case-id');
  const $successFileHash = $('#success-file-hash');
  const $successViewBtn = $('#success-view-case-btn');

  let selectedAutoFile = null;

  // File selection for Auto Ingestion
  function setAutoFile(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      LG.toast('Automated CIS extraction requires a PDF document.', 'warning');
      return;
    }
    selectedAutoFile = file;
    $autoFileLabel.html(`<i class="bi bi-file-earmark-check text-success me-2"></i>${LG.utils.escapeHtml(file.name)} (${Math.round(file.size / 1024)} KB)`);
    $autoSubmitBtn.prop('disabled', false);
  }

  $autoBrowseBtn.on('click', function () {
    $autoFileInput.trigger('click');
  });

  $autoFileInput.on('change', function () {
    if (this.files.length > 0) {
      setAutoFile(this.files[0]);
    }
  });

  // Drag and drop for Auto Ingestion
  $autoDropzone.on('dragover dragenter', function (e) {
    e.preventDefault();
    e.stopPropagation();
    $autoDropzone.addClass('dragover');
  });

  $autoDropzone.on('dragleave dragend drop', function (e) {
    e.preventDefault();
    e.stopPropagation();
    $autoDropzone.removeClass('dragover');
  });

  $autoDropzone.on('drop', function (e) {
    const files = e.originalEvent.dataTransfer.files;
    if (files.length > 0) {
      setAutoFile(files[0]);
    }
  });

  // Auto Upload Form Submit
  $autoForm.on('submit', function (e) {
    e.preventDefault();
    if (!selectedAutoFile) {
      LG.toast('Please select a PDF document to ingest.', 'warning');
      return;
    }

    $autoProgress.removeClass('d-none');
    $autoSubmitBtn.prop('disabled', true);

    const formData = new FormData();
    formData.append('file', selectedAutoFile);

    LG.api.upload.uploadAuto(formData)
      .done(function (res) {
        $successCaseId.text(res.id || 'N/A');
        $successFileHash.text(res.file_hash || 'SHA-256 Registered');
        $successViewBtn.attr('href', 'case-viewer.html?id=' + encodeURIComponent(res.id));
        $autoForm[0].reset();
        $autoFileLabel.text('Choose or Drop Judgment PDF');
        selectedAutoFile = null;
        LG.toast('Document ingested and parsed by CIS engine!', 'success');

        // Populate and display Auto-Extract Review Card
        const data = res.extracted_data || res;
        const cid = res.id || res.case_id;
        const conf = Math.round((res.overall_confidence || data.overall_confidence || 0.88) * 100);

        $('#review-case-id').val(cid);
        $('#review-display-title').text(data.title || 'Extracted Case Docket');
        $('#review-confidence-badge').html(`<i class="bi bi-check-circle-fill me-1"></i>${conf}% Confidence (${conf >= 75 ? 'High' : 'Moderate'})`);
        $('#review-sha-seal').text('SHA-256: ' + (res.file_hash ? res.file_hash.substring(0, 16) + '...' : 'Sealed'));

        $('#review-caseno').val(data.case_no || '');
        if (data.court) $('#review-court').val(data.court);
        $('#review-title').val(data.title || '');
        $('#review-judge').val(data.judge || '');
        $('#review-parties').val(data.parties || '');
        $('#review-acts').val(Array.isArray(data.act_tags) ? data.act_tags.join(', ') : (data.act_tags || ''));
        $('#review-sections').val(Array.isArray(data.section_tags) ? data.section_tags.join(', ') : (data.section_tags || ''));
        $('#review-ratio').val(data.ratio_decidendi || '');
        $('#review-summary').val(data.summary || data.facts || '');

        $('#review-split-btn').attr('href', 'case-review.html?id=' + encodeURIComponent(cid));
        $('#review-dossier-btn').attr('href', 'case-viewer.html?id=' + encodeURIComponent(cid));

        $('#auto-review-card').removeClass('d-none');
        $('html, body').animate({
          scrollTop: $('#auto-review-card').offset().top - 80
        }, 400);
      })
      .fail(function (xhr) {
        let msg = 'Failed to ingest document.';
        if (xhr.responseJSON && xhr.responseJSON.detail) {
          msg = typeof xhr.responseJSON.detail === 'string'
            ? xhr.responseJSON.detail
            : JSON.stringify(xhr.responseJSON.detail);
        }
        LG.toast(msg, 'danger');
      })
      .always(function () {
        $autoProgress.addClass('d-none');
        $autoSubmitBtn.prop('disabled', false);
      });
  });

  // Manual Upload Form Submit
  $manualForm.on('submit', function (e) {
    e.preventDefault();
    const fileInput = document.getElementById('man-file');
    if (!fileInput.files.length) {
      LG.toast('Please select a judgment file (PDF or DOCX).', 'warning');
      return;
    }

    const title = $('#man-title').val().trim();
    const caseNo = $('#man-caseno').val().trim();
    const court = $('#man-court').val();
    const year = parseInt($('#man-year').val(), 10);
    const outcome = $('#man-outcome').val();
    const judge = $('#man-judge').val().trim();
    const acts = $('#man-acts').val().trim();
    const summary = $('#man-summary').val().trim();

    $manSubmitBtn.prop('disabled', true).html(`
      <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
      <span>Uploading &amp; Hashing...</span>
    `);

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('title', title);
    formData.append('case_no', caseNo);
    formData.append('court', court);
    formData.append('year', year);
    if (outcome) formData.append('outcome', outcome);
    if (judge) formData.append('judge', judge);
    if (summary) formData.append('summary', summary);
    if (acts) {
      const tagList = acts.split(',').map(s => s.trim()).filter(Boolean);
      formData.append('act_tags', JSON.stringify(tagList));
      formData.append('section_tags', JSON.stringify(tagList));
    }

    LG.api.upload.uploadCase(formData)
      .done(function (res) {
        $successCaseId.text(res.id || 'N/A');
        $successFileHash.text(res.file_hash || 'SHA-256 Registered');
        $successViewBtn.attr('href', 'case-viewer.html?id=' + encodeURIComponent(res.id));
        $successModal.show();
        $manualForm[0].reset();
        LG.toast('Case uploaded and submitted for review!', 'success');
      })
      .fail(function (xhr) {
        let msg = 'Failed to upload case.';
        if (xhr.responseJSON && xhr.responseJSON.detail) {
          msg = typeof xhr.responseJSON.detail === 'string'
            ? xhr.responseJSON.detail
            : JSON.stringify(xhr.responseJSON.detail);
        }
        LG.toast(msg, 'danger');
      })
      .always(function () {
        $manSubmitBtn.prop('disabled', false).html(`
          <i class="bi bi-cloud-arrow-up-fill me-1"></i>
          <span>Submit for Registrar Review</span>
        `);
      });
  });

  // Approve & Seal from Review Card
  $('#review-approve-btn').on('click', function () {
    const cid = $('#review-case-id').val();
    if (!cid) return;
    const $btn = $(this);
    $btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm me-1"></span>Sealing Case...');

    LG.api.admin.approve(cid, 'Approved directly from Ingestion Review Workstation')
      .done(function () {
        LG.toast('Case successfully approved, cryptographically sealed, and published!', 'success');
        $btn.html('<i class="bi bi-check2-circle me-1"></i>Approved & Published');
        setTimeout(function () {
          window.location.href = 'case-viewer.html?id=' + encodeURIComponent(cid);
        }, 1000);
      })
      .fail(function (xhr) {
        LG.toast('Approval error or already published.', 'warning');
        $btn.prop('disabled', false).html('<i class="bi bi-shield-check me-1"></i>Approve & Seal Case');
      });
  });
});
