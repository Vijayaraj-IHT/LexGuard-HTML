/**
 * LexGuard — Public Cryptographic Verifier Controller (verify.js)
 * Web Crypto API Client-side local hash computation & Live Lookup
 * LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  const $dropzone = $('#file-dropzone');
  const $fileInput = $('#file-input');
  const $selectFileBtn = $('#select-file-btn');
  const $progressBox = $('#hashing-progress-box');
  const $progressBar = $('#hashing-bar');
  const $progressPercent = $('#hashing-percent');
  const $hashForm = $('#hash-form');
  const $hashInput = $('#hash-input');
  const $resultBox = $('#verification-result-box');
  const $resultAuthentic = $('#result-authentic');
  const $resultUnregistered = $('#result-unregistered');
  const $auditTableBody = $('#audit-table-body');

  /**
   * Perform verification lookup against backend with computed hash.
   */
  function performLookup(hash) {
    if (!hash || hash.length !== 64) {
      LG.toast('Please enter a valid 64-character hexadecimal SHA-256 hash.', 'warning');
      return;
    }

    $resultBox.removeClass('d-none');
    $resultAuthentic.addClass('d-none');
    $resultUnregistered.addClass('d-none');
    $auditTableBody.html('<tr><td colspan="4" class="text-secondary text-center">Verifying digest against the audit ledger...</td></tr>');

    LG.api.verification.lookup(hash)
      .done(function (res) {
        if (res.matched && res.case) {
          // Authentic Match
          $resultAuthentic.removeClass('d-none');
          $('#matched-case-title').text(res.case.title || 'Official Judgment');
          $('#matched-case-court').text(res.case.court || 'Court');
          $('#matched-hash-display').text(LG.crypto.formatHashBlocks(res.query_hash));
          $('#matched-caseno').text(res.case.case_no || '—');
          $('#matched-date').text(LG.utils.formatDate(res.case.decision_date || res.case.created_at));
          $('#matched-bench').text(res.case.judge || 'Hon\'ble Judges');
          $('#matched-view-btn').attr('href', 'case-viewer.html?id=' + encodeURIComponent(res.case.id));

          LG.toast('Cryptographic Seal Verified: 100% Authentic Match', 'success');
        } else {
          // Unregistered / Tampered
          $resultUnregistered.removeClass('d-none');
          $('#unregistered-hash-display').text(LG.crypto.formatHashBlocks(res.query_hash || hash));
          LG.toast('Verification Alert: Digest not found in published repository.', 'danger');
        }

        // Render Audit Logs
        // Backend returns audit_trail (last entries, each locally checked). The badge
        // reflects the real check result; it is never a static label.
        const audit = res.audit_trail || [];
        if (audit.length > 0) {
          const rows = audit.map(function (log) {
            const ok = log.recomputed_ok === true && log.link_ok === true;
            const badge = ok
              ? '<span class="text-success small font-mono"><i class="bi bi-shield-check me-1"></i>Verified</span>'
              : '<span class="text-danger small font-mono"><i class="bi bi-shield-x me-1"></i>Failed check</span>';
            return `
              <tr>
                <td class="text-secondary">${LG.utils.formatDateTime(log.timestamp || log.created_at)}</td>
                <td><span class="badge bg-secondary">${LG.utils.escapeHtml(log.action)}</span></td>
                <td class="text-light">${LG.utils.escapeHtml(log.details || 'System recorded event')}</td>
                <td>${badge}</td>
              </tr>
            `;
          }).join('');
          $auditTableBody.html(rows);
        } else {
          $auditTableBody.html(`
            <tr>
              <td colspan="4" class="text-secondary text-center">
                ${res.matched ? 'Sealed document registered in permanent judicial ledger.' : 'No audit records found for this digest.'}
              </td>
            </tr>
          `);
        }
      })
      .fail(function (xhr) {
        let msg = 'Failed to execute verification lookup.';
        if (xhr.responseJSON && xhr.responseJSON.detail) {
          msg = typeof xhr.responseJSON.detail === 'string'
            ? xhr.responseJSON.detail
            : JSON.stringify(xhr.responseJSON.detail);
        }
        $resultUnregistered.removeClass('d-none');
        $('#unregistered-hash-display').text(hash);
        LG.toast(msg, 'danger');
      });
  }

  /**
   * Compute hash from File object using client-side Web Crypto API.
   */
  function hashAndVerifyFile(file) {
    if (!file) return;

    $progressBox.removeClass('d-none');
    $progressBar.css('width', '0%');
    $progressPercent.text('0%');

    LG.crypto.sha256(file, function (percent) {
      $progressBar.css('width', percent + '%');
      $progressPercent.text(percent + '%');
    })
      .then(function (computedHash) {
        $hashInput.val(computedHash);
        $progressBox.addClass('d-none');
        LG.toast('Local Client-side SHA-256 generated in browser', 'info');
        performLookup(computedHash);
      })
      .catch(function (err) {
        $progressBox.addClass('d-none');
        LG.toast('Failed to compute hash: ' + err.message, 'danger');
      });
  }

  // Drag and drop event handlers
  $dropzone.on('dragover dragenter', function (e) {
    e.preventDefault();
    e.stopPropagation();
    $dropzone.addClass('dragover');
  });

  $dropzone.on('dragleave dragend drop', function (e) {
    e.preventDefault();
    e.stopPropagation();
    $dropzone.removeClass('dragover');
  });

  $dropzone.on('drop', function (e) {
    const files = e.originalEvent.dataTransfer.files;
    if (files.length > 0) {
      hashAndVerifyFile(files[0]);
    }
  });

  $selectFileBtn.on('click', function () {
    $fileInput.trigger('click');
  });

  $fileInput.on('change', function () {
    if (this.files.length > 0) {
      hashAndVerifyFile(this.files[0]);
    }
  });

  // Manual Hash Form Submit
  $hashForm.on('submit', function (e) {
    e.preventDefault();
    const hash = $hashInput.val().trim().toLowerCase();
    performLookup(hash);
  });

  // Check URL query param ?hash=... on load
  const initialHash = LG.utils.getQueryParam('hash');
  if (initialHash) {
    $hashInput.val(initialHash);
    performLookup(initialHash);
  }
});
