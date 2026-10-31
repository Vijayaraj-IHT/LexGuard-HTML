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
                <button type="button" class="btn btn-xs btn-judicial-outline open-review-btn" data-id="${encodeURIComponent(item.case_id)}" data-title="${LG.utils.escapeHtml(item.title)}" data-court="${LG.utils.escapeHtml(item.court)}" title="Quick Seal Modal">
                  <i class="bi bi-patch-check me-1"></i>Quick Seal
                </button>
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
   * Load Merkle Audit Logs.
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
              <td class="text-secondary">${LG.utils.formatDateTime(log.timestamp)}</td>
              <td><span class="${actionBadge}">${LG.utils.escapeHtml(log.action)}</span></td>
              <td class="text-light">${LG.utils.escapeHtml(log.details || 'Event recorded')}</td>
              <td class="font-mono text-warning small">${LG.utils.truncateHash(log.curr_hash, 6)}</td>
              <td class="font-mono text-secondary small">${LG.utils.truncateHash(log.prev_hash, 6)}</td>
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
    $chainStatusBanner.removeClass('d-none alert-success alert-danger').addClass('alert-dark')
      .html('<div class="spinner-border spinner-border-sm text-warning me-2"></div>Validating SHA-256 chain links across all historical events...');

    LG.api.admin.verifyAuditChain()
      .done(function (res) {
        if (res.is_valid) {
          $chainStatusBanner.removeClass('alert-dark alert-danger').addClass('alert-success')
            .html(`
              <div class="d-flex align-items-center gap-2">
                <i class="bi bi-shield-fill-check fs-4 text-success"></i>
                <div>
                  <strong>Cryptographic Merkle Audit Chain Verified: 100% Valid!</strong>
                  <div class="small">${res.total_records} sequential events verified with zero broken links or modifications.</div>
                </div>
              </div>
            `);
          LG.toast('Merkle Audit Chain verified 100% valid!', 'success');
        } else {
          $chainStatusBanner.removeClass('alert-dark alert-success').addClass('alert-danger')
            .html(`
              <div class="d-flex align-items-center gap-2">
                <i class="bi bi-shield-fill-x fs-4 text-danger"></i>
                <div>
                  <strong>Integrity Violation Detected!</strong>
                  <div class="small">Broken chain detected at record ID: ${res.broken_at_id || 'Unknown'}. ${res.message}</div>
                </div>
              </div>
            `);
          LG.toast('Audit chain broken! Contact administrator.', 'danger');
        }
      })
      .fail(function () {
        $chainStatusBanner.removeClass('alert-dark alert-success').addClass('alert-danger')
          .text('Failed to execute cryptographic verification.');
      });
  });

  /**
   * Load and render Staff Password Reset Tickets (Supervisor Four-Eyes Gate)
   */
  function loadStaffResetTickets() {
    LG.api.request('/admin/password-reset-tickets', 'GET')
      .done(function (tickets) {
        const $tbody = $('#staff-reset-tickets-tbody');
        const $badge = $('#staff-tickets-badge-count');

        if (!Array.isArray(tickets) || tickets.length === 0) {
          $tbody.html(`
            <tr>
              <td colspan="5" class="text-center py-3 text-secondary">
                <i class="bi bi-check2-circle text-success me-1"></i>No pending staff password reset tickets.
              </td>
            </tr>
          `);
          $badge.text('0 Tickets').removeClass('bg-danger').addClass('badge-gold');
          return;
        }

        $badge.text(`${tickets.length} Pending`).removeClass('badge-gold').addClass('bg-danger');

        const rows = tickets.map(function (t) {
          return `
            <tr>
              <td>
                <div class="fw-bold text-light">${LG.utils.escapeHtml(t.user_name)}</div>
                <div class="text-secondary small font-mono">${LG.utils.escapeHtml(t.user_id)}</div>
              </td>
              <td>
                <div>${LG.utils.escapeHtml(t.user_email)}</div>
                <span class="badge badge-gold" style="font-size: 0.7rem;">${LG.utils.escapeHtml(t.role)}</span>
              </td>
              <td>
                <span class="font-mono text-warning">${LG.utils.escapeHtml(t.credential_id || 'N/A')}</span>
              </td>
              <td class="text-secondary small">
                ${LG.utils.formatDate(t.submitted_at)}
              </td>
              <td class="text-end">
                <button type="button" class="btn btn-xs btn-gold authorize-staff-reset-btn" data-ticket-id="${LG.utils.escapeHtml(t.ticket_id)}" data-user-name="${LG.utils.escapeHtml(t.user_name)}">
                  <i class="bi bi-shield-check me-1"></i>Authorize Reset
                </button>
              </td>
            </tr>
          `;
        }).join('');

        $tbody.html(rows);

        $('.authorize-staff-reset-btn').off('click').on('click', function () {
          const ticketId = $(this).data('ticket-id');
          const userName = $(this).data('user-name');
          const $btn = $(this);

          if (!confirm(`Are you sure you want to authorize a one-time password reset link for court officer ${userName}?`)) {
            return;
          }

          $btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm me-1"></span>Authorizing...');

          LG.api.request(`/admin/authorize-password-reset/${encodeURIComponent(ticketId)}`, 'POST')
            .done(function (res) {
              LG.toast(`Staff password reset authorized for ${userName}!`, 'success');
              alert(`SUPERVISOR AUTHORIZATION GRANTED!\n\nOne-Time Activation URL for ${userName}:\n${window.location.origin}${res.reset_url}\n\nValid for 60 minutes. Provide this link securely to the officer.`);
              loadStaffResetTickets();
            })
            .fail(function (xhr) {
              $btn.prop('disabled', false).html('<i class="bi bi-shield-check me-1"></i>Authorize Reset');
              let err = 'Failed to authorize reset ticket.';
              if (xhr.responseJSON && xhr.responseJSON.detail) {
                err = xhr.responseJSON.detail;
              }
              LG.toast(err, 'danger');
            });
        });
      })
      .fail(function () {
        // Silently omit if not senior staff
        $('#staff-reset-tickets-section').addClass('d-none');
      });
  }

  // Refresh Button
  $refreshBtn.on('click', function () {
    loadAnalytics();
    loadApprovalQueue();
    loadAuditLogs();
    loadStaffResetTickets();
    LG.toast('Workstation data refreshed.', 'info');
  });

  // Initial Load
  loadAnalytics();
  loadApprovalQueue();
  loadAuditLogs();
  loadStaffResetTickets();
});
