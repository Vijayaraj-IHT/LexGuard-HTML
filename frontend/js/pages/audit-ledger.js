/**
 * LexGuard — Cryptographic Merkle Audit Ledger Controller (audit-ledger.js)
 * Semester 5 Project · LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  // 1. Strict Staff RBAC Guard
  if (!LG.requireAuth(['staff', 'court_staff', 'senior_staff'])) {
    return;
  }

  let allLogs = [];
  const $tbody = $('#audit-logs-tbody');
  const $countSummary = $('#audit-count-summary');
  const $actionFilter = $('#audit-action-filter');
  const $searchInput = $('#audit-search-input');
  const $verifyBtn = $('#verify-chain-btn');
  const $refreshBtn = $('#refresh-audit-btn');

  // Chain status elements
  const $chainCard = $('#chain-status-card');
  const $chainIcon = $('#chain-icon-wrap');
  const $chainTitle = $('#chain-status-title');
  const $chainSubtitle = $('#chain-status-subtitle');
  const $chainTotalBadge = $('#chain-total-badge');

  // Modal elements
  const hashModal = new bootstrap.Modal(document.getElementById('hashModal'));
  const $modalCurrHash = $('#modal-curr-hash');
  const $modalPrevHash = $('#modal-prev-hash');
  const $modalAction = $('#modal-action');
  const $modalTime = $('#modal-time');
  const $modalDetails = $('#modal-details');

  function getActionBadge(action) {
    switch (action) {
      case 'VIEW_DOCUMENT':
        return '<span class="badge bg-primary bg-opacity-20 text-info border border-info border-opacity-25"><i class="bi bi-eye me-1"></i>VIEW</span>';
      case 'DOWNLOAD_DOCUMENT':
        return '<span class="badge bg-warning bg-opacity-20 text-warning border border-warning border-opacity-25"><i class="bi bi-download me-1"></i>DOWNLOAD</span>';
      case 'VERIFY_INTEGRITY':
        return '<span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-25"><i class="bi bi-shield-check me-1"></i>VERIFY</span>';
      case 'INGEST_OFFICIAL':
        return '<span class="badge bg-purple bg-opacity-20 text-purple border border-purple border-opacity-25" style="background:#581c87; color:#d8b4fe;"><i class="bi bi-cloud-arrow-up me-1"></i>INGEST</span>';
      case 'APPROVE_CASE':
        return '<span class="badge badge-gold"><i class="bi bi-check2-circle me-1"></i>APPROVE</span>';
      default:
        return `<span class="badge bg-secondary">${LG.utils.escapeHtml(action)}</span>`;
    }
  }

  function renderTable(logs) {
    if (!logs || logs.length === 0) {
      $tbody.html(`
        <tr>
          <td colspan="7" class="text-center py-5 text-secondary">
            <i class="bi bi-inbox fs-2 mb-2 d-block"></i>
            No cryptographic audit records matching the specified criteria.
          </td>
        </tr>
      `);
      $countSummary.text('Showing 0 records');
      return;
    }

    $countSummary.text(`Showing ${logs.length} records`);

    const rows = logs.map(function (log) {
      const timeStr = log.timestamp ? new Date(log.timestamp).toISOString().replace('T', ' ').slice(0, 19) : '—';
      const shortHash = log.current_hash ? log.current_hash.substring(0, 12) + '...' : '—';
      const userStr = log.user_id ? log.user_id.substring(0, 8) + '...' : 'Public / API';
      const caseStr = log.case_id ? `<a href="case-viewer.html?id=${encodeURIComponent(log.case_id)}" class="text-warning text-decoration-none font-mono small">${log.case_id.substring(0, 8)}...</a>` : '<span class="text-secondary small">—</span>';

      return `
        <tr>
          <td class="ps-4 font-mono small text-secondary">${timeStr}</td>
          <td>${getActionBadge(log.action)}</td>
          <td>${caseStr}</td>
          <td class="font-mono small text-light">${userStr}</td>
          <td class="small text-secondary font-mono">${LG.utils.escapeHtml(log.ip_address || '127.0.0.1')}</td>
          <td>
            <button type="button" class="btn btn-xs btn-outline-secondary font-mono text-warning inspect-hash-btn" data-curr="${LG.utils.escapeHtml(log.current_hash || '')}" data-prev="${LG.utils.escapeHtml(log.previous_log_hash || '')}" data-action="${LG.utils.escapeHtml(log.action || '')}" data-time="${timeStr}" data-details="${LG.utils.escapeHtml(log.details || '')}">
              <i class="bi bi-fingerprint me-1"></i>${shortHash}
            </button>
          </td>
          <td class="pe-4 text-end">
            <button type="button" class="btn btn-xs btn-judicial-outline view-detail-btn" data-curr="${LG.utils.escapeHtml(log.current_hash || '')}" data-prev="${LG.utils.escapeHtml(log.previous_log_hash || '')}" data-action="${LG.utils.escapeHtml(log.action || '')}" data-time="${timeStr}" data-details="${LG.utils.escapeHtml(log.details || '')}">
              Details
            </button>
          </td>
        </tr>
      `;
    }).join('');

    $tbody.html(rows);

    // Attach click handler to inspect modal
    $('.inspect-hash-btn, .view-detail-btn').on('click', function () {
      $modalCurrHash.text($(this).data('curr'));
      $modalPrevHash.text($(this).data('prev') || 'GENESIS BLOCK HASH');
      $modalAction.text($(this).data('action'));
      $modalTime.text($(this).data('time'));
      $modalDetails.text($(this).data('details'));
      hashModal.show();
    });
  }

  function applyFilters() {
    let filtered = allLogs;
    const action = $actionFilter.val();
    const query = $searchInput.val().trim().toLowerCase();

    if (action) {
      filtered = filtered.filter(l => l.action === action);
    }
    if (query) {
      filtered = filtered.filter(l => {
        return (l.details && l.details.toLowerCase().includes(query)) ||
               (l.case_id && l.case_id.toLowerCase().includes(query)) ||
               (l.user_id && l.user_id.toLowerCase().includes(query)) ||
               (l.ip_address && l.ip_address.toLowerCase().includes(query)) ||
               (l.current_hash && l.current_hash.toLowerCase().includes(query));
      });
    }

    renderTable(filtered);
  }

  function loadAuditLogs() {
    $tbody.html(`
      <tr>
        <td colspan="7" class="text-center py-5 text-secondary">
          <div class="spinner-border spinner-border-sm text-warning me-2"></div>
          Loading cryptographic audit records from PostgreSQL...
        </td>
      </tr>
    `);

    LG.api.request({
      url: '/admin/audit-logs?limit=200',
      method: 'GET'
    })
    .done(function (res) {
      allLogs = Array.isArray(res) ? res : (res.logs || []);
      $chainTotalBadge.text(`Total Records: ${allLogs.length}`);
      applyFilters();
    })
    .fail(function () {
      $tbody.html(`
        <tr>
          <td colspan="7" class="text-center py-5 text-danger">
            <i class="bi bi-exclamation-triangle me-1"></i>Failed to load cryptographic audit ledger.
          </td>
        </tr>
      `);
    });
  }

  function verifyEntireChain() {
    $verifyBtn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm me-1"></span>Verifying Chain...');

    LG.api.request({
      url: '/admin/verify-audit-chain',
      method: 'GET'
    })
    .done(function (res) {
      if (res.is_valid) {
        $chainCard.css('border-color', '#10b981');
        $chainIcon.attr('class', 'p-2 rounded bg-success bg-opacity-10 border border-success border-opacity-25')
          .html('<i class="bi bi-shield-fill-check text-success fs-3"></i>');
        $chainTitle.html('<span class="text-success"><i class="bi bi-check-circle-fill me-1"></i>Cryptographic Merkle Chain: 100% Verified &amp; Untampered</span>');
        $chainSubtitle.text(`All ${res.total_records} sequence blocks cryptographically validated against SHA-256 parent digests.`);
        LG.toast('Merkle hash chain is 100% valid and verified.', 'success');
      } else {
        $chainCard.css('border-color', '#f59e0b');
        $chainIcon.attr('class', 'p-2 rounded bg-warning bg-opacity-10 border border-warning border-opacity-25')
          .html('<i class="bi bi-shield-exclamation text-warning fs-3"></i>');
        $chainTitle.html('<span class="text-warning"><i class="bi bi-exclamation-triangle-fill me-1"></i>Chain Structure Audited</span>');
        $chainSubtitle.text(`${res.message || 'Audit check completed.'} Total blocks: ${res.total_records}`);
        LG.toast(res.message || 'Chain validation completed.', 'info');
      }
    })
    .fail(function () {
      LG.toast('Audit chain verification failed.', 'danger');
    })
    .always(function () {
      $verifyBtn.prop('disabled', false).html('<i class="bi bi-link-45deg me-1"></i>Verify Entire Hash Chain');
    });
  }

  // Wire up handlers
  $actionFilter.on('change', applyFilters);
  $searchInput.on('input', applyFilters);
  $verifyBtn.on('click', verifyEntireChain);
  $refreshBtn.on('click', loadAuditLogs);

  // Initial load
  loadAuditLogs();
});
