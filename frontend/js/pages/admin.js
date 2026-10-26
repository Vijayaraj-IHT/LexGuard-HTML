/**
 * LexGuard — Staff Workstation & Admin Controller (admin.js)
 * LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  // 1. Strict RBAC Guard: Requires Staff / Court Staff / Senior Staff
  if (!LG.requireAuth(['staff', 'court_staff', 'senior_staff'])) {
    return;
  }

  const canDecideCases = LG.session.hasRole(['senior_staff']);
  let doughnutChart = null;
  let barChart = null;

  const $kpiTotalCases = $('#kpi-total-cases');
  const $kpiPublishedCases = $('#kpi-published-cases');
  const $kpiPendingCases = $('#kpi-pending-cases');
  const $kpiTotalAudit = $('#kpi-total-audit');
  const $queueBadgeCount = $('#queue-badge-count');

  const $queueTableBody = $('#queue-table-body');
  const $auditLogsTableBody = $('#audit-logs-table-body');
  const $verifyChainBtn = $('#verify-chain-btn');
  const $chainStatusBanner = $('#chain-status-banner');
  const $refreshBtn = $('#refresh-admin-btn');

  // Review Modal Elements
  const $reviewModal = new bootstrap.Modal(document.getElementById('reviewModal'));
  const $modalCaseId = $('#modal-case-id');
  const $modalCaseTitle = $('#modal-case-title');
  const $modalCaseCourt = $('#modal-case-court');
  const $modalReviewNote = $('#modal-review-note');
  const $modalApproveBtn = $('#modal-approve-btn');
  const $modalRejectBtn = $('#modal-reject-btn');

  /**
   * Load Analytics KPIs and Chart.js visualizations.
   */
  function loadAnalytics() {
    LG.api.admin.getAnalytics()
      .done(function (res) {
        const cases = res.cases || {};
        const audit = res.audit || {};
        const users = res.users || {};

        $kpiTotalCases.text(cases.total || 0);
        $kpiPublishedCases.text(cases.published || 0);
        $kpiPendingCases.text(cases.pending_approval || 0);
        $kpiTotalAudit.text(audit.total_events || 0);
        $queueBadgeCount.text(cases.pending_approval || 0);

        renderDoughnutChart(cases);
        renderBarChart(users.by_role || {});
      })
      .fail(function () {
        LG.toast('Failed to load administrative analytics.', 'danger');
      });
  }

  /**
   * Render Chart.js Cases Doughnut Chart.
   */
  function renderDoughnutChart(cases) {
    const ctx = document.getElementById('cases-doughnut-chart');
    if (!ctx) return;

    if (doughnutChart) doughnutChart.destroy();

    doughnutChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Sealed & Published', 'Pending Review', 'Quarantined'],
        datasets: [{
          data: [cases.published || 0, cases.pending_approval || 0, cases.quarantined || 0],
          backgroundColor: ['#059669', '#d97706', '#991b1b'],
          borderColor: '#ffffff',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: '#0f172a', font: { family: 'Inter', size: 12, weight: '600' } }
          }
        }
      }
    });
  }

  /**
   * Render Chart.js Users by Role Bar Chart.
   */
  function renderBarChart(roles) {
    const ctx = document.getElementById('users-bar-chart');
    if (!ctx) return;

    if (barChart) barChart.destroy();

    const labels = Object.keys(roles).map(LG.utils.getRoleDisplayName);
    const data = Object.values(roles);

    barChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels.length > 0 ? labels : ['Court Staff', 'Advocates', 'Scholars', 'Public'],
        datasets: [{
          label: 'Registered Accounts',
          data: data.length > 0 ? data : [2, 12, 6, 24],
          backgroundColor: '#991b1b',
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: { color: '#475569' },
            grid: { color: 'rgba(185, 28, 28, 0.08)' }
          },
          x: {
            ticks: { color: '#0f172a', font: { weight: '600' } },
            grid: { display: false }
          }
        },
        plugins: {
          legend: { display: false }
        }
      }
    });
  }

  /**
   * Load Pending Approval Queue.
   */
  function loadApprovalQueue() {
    LG.api.admin.getQueue()
      .done(function (queue) {
        if (!Array.isArray(queue) || queue.length === 0) {
          $queueTableBody.html(`
            <tr>
              <td colspan="6" class="text-center py-5 text-secondary">
                <i class="bi bi-check2-circle fs-2 text-success d-block mb-2"></i>
                <div class="fw-semibold text-light">Approval queue is currently empty</div>
                <div class="small">All ingested court cases have been cryptographically sealed and published.</div>
              </td>
            </tr>
          `);
          $queueBadgeCount.text('0');
          return;
        }

        $queueBadgeCount.text(queue.length);

        const rows = queue.map(function (item) {
          return `
            <tr>
              <td>
                <div class="fw-bold text-light">${LG.utils.escapeHtml(item.title)}</div>
                <div class="small text-secondary">Case No: ${LG.utils.escapeHtml(item.case_no)}</div>
              </td>
              <td><span class="${LG.utils.courtBadgeClass(item.court)}">${LG.utils.escapeHtml(item.court)}</span></td>
              <td class="text-light">${item.year || '—'}</td>
              <td class="text-secondary">${LG.utils.escapeHtml(item.submitted_by || 'Staff')}</td>
              <td class="font-mono text-warning small">${LG.utils.truncateHash(item.file_hash, 6)}</td>
              <td class="text-end">
                <a href="case-review.html?id=${encodeURIComponent(item.case_id)}" class="btn btn-xs btn-gold me-1" title="Open Split-Screen Review Workstation">
                  <i class="bi bi-columns me-1"></i>Split-Screen Review
                </a>
                ${canDecideCases ? `
                <button type="button" class="btn btn-xs btn-judicial-outline open-review-btn" data-id="${encodeURIComponent(item.case_id)}" data-title="${LG.utils.escapeHtml(item.title)}" data-court="${LG.utils.escapeHtml(item.court)}" title="Quick Seal Modal (senior staff)">
                  <i class="bi bi-patch-check me-1"></i>Quick Seal
                </button>` : '<span class="badge bg-secondary" title="Approval and rejection require senior staff who did not submit the case">Senior review required</span>'}
              </td>
            </tr>
          `;
        }).join('');

        $queueTableBody.html(rows);

        $('.open-review-btn').on('click', function () {
          const cid = $(this).data('id');
          const title = $(this).data('title');
          const court = $(this).data('court');
          $modalCaseId.val(cid);
          $modalCaseTitle.text(title);
          $modalCaseCourt.text(court);
          $modalReviewNote.val('');
          $reviewModal.show();
        });
      })
      .fail(function () {
        $queueTableBody.html('<tr><td colspan="6" class="text-center text-danger py-4">Failed to load queue.</td></tr>');
      });
  }

  /**
   * Approve / Reject Action Handlers.
   */
  $modalApproveBtn.on('click', function () {
    const cid = $modalCaseId.val();
    const note = $modalReviewNote.val().trim() || 'Verified against certified record.';

    LG.api.request({
      url: '/admin/approve/' + encodeURIComponent(cid),
      method: 'POST',
      data: {
        status: 'published',
        review_note: note
      }
    })
      .done(function () {
        LG.toast('Composite judicial seal (Phi_case) affixed! Case published.', 'success');
        $reviewModal.hide();
        loadApprovalQueue();
        loadAnalytics();
        loadAuditLogs();
      })
      .fail(function () {
        LG.toast('Failed to approve case record.', 'danger');
      });
  });

  $modalRejectBtn.on('click', function () {
    const cid = $modalCaseId.val();
    const note = $modalReviewNote.val().trim() || 'Procedural discrepancy in CIS extraction.';

    LG.api.request({
      url: '/admin/approve/' + encodeURIComponent(cid),
      method: 'POST',
      data: {
        status: 'rejected',
        review_note: note
      }
    })
      .done(function () {
        LG.toast('Submission rejected.', 'warning');
        $reviewModal.hide();
        loadApprovalQueue();
        loadAnalytics();
      })
      .fail(function () {
        LG.toast('Failed to reject submission.', 'danger');
      });
  });

  /**
   * Load hash-chained audit logs.
   */
  function loadAuditLogs() {
    LG.api.admin.getAuditLogs(30)
      .done(function (logs) {
        if (!Array.isArray(logs) || logs.length === 0) {
          $auditLogsTableBody.html('<tr><td colspan="5" class="text-center py-4 text-secondary">No audit entries found.</td></tr>');
          return;
        }

        const rows = logs.map(function (log) {
          let actionBadge = 'badge bg-secondary';
          if (log.action === 'APPROVE') actionBadge = 'badge bg-success';
          else if (log.action === 'REJECT' || log.action === 'INTEGRITY_VIOLATION') actionBadge = 'badge bg-danger';
          else if (log.action === 'LOGIN') actionBadge = 'badge bg-primary';
          else if (log.action === 'DRAFT_ANALYZE') actionBadge = 'badge bg-info text-dark';

          return `
            <tr>
              <td class="text-secondary">${LG.utils.formatDateTime(log.timestamp)}${log.seq != null ? `<div class="small font-mono">#${log.seq} · segment ${log.segment != null ? log.segment : '—'}</div>` : ''}</td>
              <td><span class="${actionBadge}">${LG.utils.escapeHtml(log.action)}</span></td>
              <td class="text-light">${LG.utils.escapeHtml(log.details || 'Event recorded')}</td>
              <td class="font-mono text-warning small">${LG.utils.truncateHash(log.current_hash, 6)}</td>
              <td class="font-mono text-secondary small">${LG.utils.truncateHash(log.previous_log_hash, 6)}</td>
            </tr>
          `;
        }).join('');

        $auditLogsTableBody.html(rows);
      })
      .fail(function () {
        $auditLogsTableBody.html('<tr><td colspan="5" class="text-center text-danger py-4">Failed to load audit logs.</td></tr>');
      });
  }

  /**
   * Verify Entire Cryptographic Audit Chain.
   */
  $verifyChainBtn.on('click', function () {
    $chainStatusBanner.removeClass('d-none alert-success alert-danger alert-warning').addClass('alert-dark')
      .html('<div class="spinner-border spinner-border-sm text-warning me-2"></div>Validating SHA-256 chain links across all historical events...');

    LG.api.admin.verifyAuditChain()
      .done(function (res) {
        const segments = Array.isArray(res.segments) ? res.segments : [];
        const archivedInvalid = segments.filter(function (segment) {
          return !segment.is_valid && segment.segment !== res.active_segment;
        });
        const safeMessage = LG.utils.escapeHtml(res.message || 'Verification finished.');

        if (res.is_valid && archivedInvalid.length === 0) {
          $chainStatusBanner.removeClass('alert-dark alert-danger alert-warning').addClass('alert-success')
            .html(`
              <div class="d-flex align-items-center gap-2">
                <i class="bi bi-shield-fill-check fs-4 text-success"></i>
                <div>
                  <strong>Hash-Chained Audit Ledger Verified</strong>
                  <div class="small">${res.active_records != null ? res.active_records : res.total_records} active-segment events verified. ${safeMessage}</div>
                </div>
              </div>
            `);
          LG.toast('Active audit segment verified.', 'success');
        } else if (res.is_valid) {
          $chainStatusBanner.removeClass('alert-dark alert-success alert-danger').addClass('alert-warning')
            .html(`
              <div class="d-flex align-items-center gap-2">
                <i class="bi bi-shield-exclamation fs-4 text-warning"></i>
                <div>
                  <strong>Active Segment Valid — Archived Segment Invalid/Superseded</strong>
                  <div class="small">${safeMessage}</div>
                </div>
              </div>
            `);
          LG.toast('Active segment valid; archived invalid segment retained for disclosure.', 'warning');
        } else {
          $chainStatusBanner.removeClass('alert-dark alert-success alert-warning').addClass('alert-danger')
            .html(`
              <div class="d-flex align-items-center gap-2">
                <i class="bi bi-shield-fill-x fs-4 text-danger"></i>
                <div>
                  <strong>Audit Chain Invalid</strong>
                  <div class="small">Broken chain detected at record ID: ${LG.utils.escapeHtml(res.broken_at_id || 'Unknown')}. ${safeMessage}</div>
                </div>
              </div>
            `);
          LG.toast('Audit chain invalid. Contact a senior administrator.', 'danger');
        }
      })
      .fail(function () {
        $chainStatusBanner.removeClass('alert-dark alert-success alert-warning').addClass('alert-danger')
          .text('Failed to execute cryptographic verification.');
      });
  });

  // Refresh Button
  $refreshBtn.on('click', function () {
    loadAnalytics();
    loadApprovalQueue();
    loadAuditLogs();
    LG.toast('Workstation data refreshed.', 'info');
  });

  // Initial Load
  loadAnalytics();
  loadApprovalQueue();
  loadAuditLogs();
});
