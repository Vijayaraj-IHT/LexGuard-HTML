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
  const isSeniorAdmin = canDecideCases;
  const currentAdmin = LG.session.user() || {};
  let doughnutChart = null;
  let barChart = null;
  let adminUsers = [];
  let adminUsersById = new Map();
  let usersLoaded = false;

  if (isSeniorAdmin) {
    $('#users-tab-item').removeClass('d-none');
    $('#open-reseal-btn').removeClass('d-none');
    $('#admin-privilege-badge').html('<i class="bi bi-person-badge-fill me-1"></i>Senior Registrar Privilege');
  } else {
    $('#admin-privilege-badge').html('<i class="bi bi-person-badge-fill me-1"></i>Court Staff Privilege');
  }

  const $kpiTotalCases = $('#kpi-total-cases');
  const $kpiPublishedCases = $('#kpi-published-cases');
  const $kpiPendingCases = $('#kpi-pending-cases');
  const $kpiTotalAudit = $('#kpi-total-audit');
  const $queueBadgeCount = $('#queue-badge-count');

  const $queueTableBody = $('#queue-table-body');
  const $auditLogsTableBody = $('#audit-logs-table-body');
  const $verifyChainBtn = $('#verify-chain-btn');
  const $chainStatusBanner = $('#chain-status-banner');
  const $chainSegmentsWrap = $('#chain-segments-wrap');
  const $chainSegmentsBody = $('#chain-segments-body');
  const $refreshBtn = $('#refresh-admin-btn');
  const $postureAudit = $('#posture-audit');
  const $postureReadiness = $('#posture-readiness');

  const $usersTableBody = $('#users-table-body');
  const $usersSearchInput = $('#users-search-input');
  const $usersRoleFilter = $('#users-role-filter');
  const $usersStatusFilter = $('#users-status-filter');
  const $usersResultCount = $('#users-result-count');

  // Review Modal Elements
  const $reviewModal = new bootstrap.Modal(document.getElementById('reviewModal'));
  const $modalCaseId = $('#modal-case-id');
  const $modalCaseTitle = $('#modal-case-title');
  const $modalCaseCourt = $('#modal-case-court');
  const $modalReviewNote = $('#modal-review-note');
  const $modalApproveBtn = $('#modal-approve-btn');
  const $modalRejectBtn = $('#modal-reject-btn');

  const createUserModalEl = document.getElementById('createUserModal');
  const editUserModalEl = document.getElementById('editUserModal');
  const resealModalEl = document.getElementById('resealModal');
  const $createUserModal = createUserModalEl ? new bootstrap.Modal(createUserModalEl) : null;
  const $editUserModal = editUserModalEl ? new bootstrap.Modal(editUserModalEl) : null;
  const $resealModal = resealModalEl ? new bootstrap.Modal(resealModalEl) : null;

  function apiErrorMessage(xhr, fallback) {
    try {
      const detail = xhr && xhr.responseJSON ? xhr.responseJSON.detail : null;
      if (typeof detail === 'string' && detail) return detail;
      if (Array.isArray(detail) && detail.length) {
        return detail.map(function (item) { return item.msg || JSON.stringify(item); }).join('; ');
      }
      if (detail) return JSON.stringify(detail);
    } catch (e) {}
    return fallback;
  }

  function setPosture($el, state, html) {
    if (!$el.length) return;
    const classes = {
      ok: 'fw-bold text-success',
      warn: 'fw-bold text-warning',
      bad: 'fw-bold text-danger'
    };
    $el.attr('class', classes[state] || classes.warn).html(html);
  }

  function loadSystemReadiness() {
    if (!LG.api.system || !LG.api.system.readiness) return;
    LG.api.system.readiness()
      .done(function (res) {
        const checks = res.checks || {};
        setPosture(
          $postureReadiness,
          'ok',
          '<i class="bi bi-check-circle-fill me-1"></i>Ready · DB/schema/storage OK'
        );
        $postureReadiness.attr('title', 'Checks: ' + JSON.stringify(checks));
      })
      .fail(function (xhr) {
        const res = xhr.responseJSON || {};
        const checks = res.checks || {};
        const failed = Object.keys(checks).filter(function (key) { return !checks[key]; });
        setPosture(
          $postureReadiness,
          'bad',
          '<i class="bi bi-exclamation-octagon-fill me-1"></i>Not ready' +
            (failed.length ? ': ' + LG.utils.escapeHtml(failed.join(', ')) : '')
        );
      });
  }

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
      .fail(function (xhr) {
        LG.toast(apiErrorMessage(xhr, 'Failed to approve case record.'), 'danger');
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
      .fail(function (xhr) {
        LG.toast(apiErrorMessage(xhr, 'Failed to reject submission.'), 'danger');
      });
  });

  /**
   * Senior-staff user administration.
   */
  function renderUsers() {
    const query = ($usersSearchInput.val() || '').toLowerCase().trim();
    const visible = adminUsers.filter(function (user) {
      if (!query) return true;
      return [user.name, user.email, user.credential_id || '', user.role, user.status]
        .join(' ')
        .toLowerCase()
        .includes(query);
    });

    $usersResultCount.text(
      'Showing ' + visible.length + ' of ' + adminUsers.length + ' loaded account(s).'
    );

    if (!visible.length) {
      $usersTableBody.html(
        '<tr><td colspan="6" class="text-center py-4 text-secondary">No users match the current filters.</td></tr>'
      );
      return;
    }

    const rows = visible.map(function (user) {
      const isSelf = String(user.id) === String(currentAdmin.id || '');
      return `
        <tr>
          <td>
            <div class="fw-bold text-light">${LG.utils.escapeHtml(user.name)}${isSelf ? ' <span class="badge bg-warning text-dark ms-1">You</span>' : ''}</div>
            <div class="small text-secondary">${LG.utils.escapeHtml(user.email)}</div>
          </td>
          <td>
            ${LG.utils.getRoleBadge(user.role)}
            <div class="small text-secondary font-mono mt-1">${LG.utils.escapeHtml(user.role)}</div>
          </td>
          <td><span class="${LG.utils.statusBadgeClass(user.status)}">${LG.utils.escapeHtml(user.status)}</span></td>
          <td class="text-secondary font-mono small">${LG.utils.escapeHtml(user.credential_id || '—')}</td>
          <td class="text-secondary">${LG.utils.formatDate(user.created_at)}</td>
          <td class="text-end">
            <button type="button" class="btn btn-xs btn-judicial-outline edit-user-btn" data-user-id="${LG.utils.escapeHtml(user.id)}">
              <i class="bi bi-person-gear me-1"></i>Edit
            </button>
          </td>
        </tr>
      `;
    }).join('');

    $usersTableBody.html(rows);
  }

  function loadUsers() {
    if (!isSeniorAdmin) return;

    const params = { limit: 500 };
    const role = $usersRoleFilter.val();
    const userStatus = $usersStatusFilter.val();
    if (role) params.role = role;
    if (userStatus) params.status = userStatus;

    $usersTableBody.html(
      '<tr><td colspan="6" class="text-center py-4 text-secondary">' +
      '<div class="spinner-border spinner-border-sm text-warning me-2"></div>Loading users…</td></tr>'
    );

    LG.api.admin.getUsers(params)
      .done(function (users) {
        adminUsers = Array.isArray(users) ? users : [];
        adminUsersById = new Map(adminUsers.map(function (user) { return [String(user.id), user]; }));
        usersLoaded = true;
        renderUsers();
      })
      .fail(function (xhr) {
        usersLoaded = false;
        $usersTableBody.html(
          '<tr><td colspan="6" class="text-center text-danger py-4">' +
          LG.utils.escapeHtml(apiErrorMessage(xhr, 'Failed to load users.')) +
          '</td></tr>'
        );
      });
  }

  function openEditUser(user) {
    if (!user || !$editUserModal) return;
    const isSelf = String(user.id) === String(currentAdmin.id || '');

    $('#edit-user-id').val(user.id);
    $('#edit-user-name').val(user.name || '');
    $('#edit-user-email').val(user.email || '');
    $('#edit-user-role').val(user.role || 'public').prop('disabled', isSelf);
    $('#edit-user-status').val(user.status || 'active').prop('disabled', isSelf);
    $('#edit-user-credential').val(user.credential_id || '');
    $editUserModal.show();
  }

  $('#tab-users-btn').on('shown.bs.tab', function () {
    if (!usersLoaded) loadUsers();
  });
  $('#refresh-users-btn').on('click', loadUsers);
  $usersRoleFilter.on('change', loadUsers);
  $usersStatusFilter.on('change', loadUsers);
  $usersSearchInput.on('input', renderUsers);
  $usersTableBody.on('click', '.edit-user-btn', function () {
    openEditUser(adminUsersById.get(String($(this).data('user-id'))));
  });

  $('#open-create-user-btn').on('click', function () {
    if (!$createUserModal) return;
    $('#create-user-form')[0].reset();
    $('#create-user-role').val('court_staff');
    $('#create-user-status').val('active');
    $createUserModal.show();
  });

  $('#create-user-form').on('submit', function (event) {
    event.preventDefault();
    const $submit = $('#create-user-submit-btn').prop('disabled', true);
    const credential = $('#create-user-credential').val().trim();

    LG.api.admin.createUser({
      name: $('#create-user-name').val().trim(),
      email: $('#create-user-email').val().trim(),
      password: $('#create-user-password').val(),
      role: $('#create-user-role').val(),
      status: $('#create-user-status').val(),
      credential_id: credential || null
    })
      .done(function () {
        if ($createUserModal) $createUserModal.hide();
        LG.toast('Account provisioned and audit-logged.', 'success');
        loadUsers();
        loadAnalytics();
        loadAuditLogs();
      })
      .fail(function (xhr) {
        LG.toast(apiErrorMessage(xhr, 'Failed to provision account.'), 'danger');
      })
      .always(function () {
        $submit.prop('disabled', false);
      });
  });

  $('#edit-user-form').on('submit', function (event) {
    event.preventDefault();
    const userId = $('#edit-user-id').val();
    const original = adminUsersById.get(String(userId)) || {};
    const next = {
      name: $('#edit-user-name').val().trim(),
      role: $('#edit-user-role').val(),
      status: $('#edit-user-status').val(),
      credential_id: $('#edit-user-credential').val().trim() || null
    };
    const updates = {};
    Object.keys(next).forEach(function (field) {
      const previous = field === 'credential_id' ? (original[field] || null) : original[field];
      if (next[field] !== previous) updates[field] = next[field];
    });

    if (!Object.keys(updates).length) {
      LG.toast('No account changes to save.', 'info');
      if ($editUserModal) $editUserModal.hide();
      return;
    }

    const $submit = $('#edit-user-submit-btn').prop('disabled', true);
    LG.api.admin.updateUser(userId, updates)
      .done(function (updated) {
        if ($editUserModal) $editUserModal.hide();
        if (String(userId) === String(currentAdmin.id || '')) {
          LG.session.set(updated);
        }
        LG.toast('Account updated and audit-logged.', 'success');
        loadUsers();
        loadAnalytics();
        loadAuditLogs();
      })
      .fail(function (xhr) {
        LG.toast(apiErrorMessage(xhr, 'Failed to update account.'), 'danger');
      })
      .always(function () {
        $submit.prop('disabled', false);
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
          else if (log.action === 'CHAIN_RESEALED') actionBadge = 'badge bg-warning text-dark';
          else if (log.action === 'USER_CREATED' || log.action === 'USER_UPDATED') actionBadge = 'badge bg-info text-dark';

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

  function renderChainSegments(segments, activeSegment) {
    if (!Array.isArray(segments) || !segments.length) {
      $chainSegmentsWrap.addClass('d-none');
      $chainSegmentsBody.empty();
      return;
    }

    const rows = segments.map(function (segment) {
      const isActive = segment.segment === activeSegment;
      const label = segment.is_valid
        ? (isActive ? 'Active · Valid' : 'Archived · Valid')
        : (isActive ? 'Active · Invalid' : 'Archived · Invalid/Superseded');
      const badge = segment.is_valid
        ? 'badge bg-success'
        : (isActive ? 'badge bg-danger' : 'badge bg-warning text-dark');
      return `
        <tr>
          <td class="font-mono text-light">${segment.segment}</td>
          <td><span class="${badge}">${label}</span></td>
          <td class="text-light">${segment.total_records != null ? segment.total_records : '—'}</td>
          <td class="text-secondary font-mono small">${segment.broken_at_index != null ? 'index ' + segment.broken_at_index : '—'}</td>
          <td class="text-secondary">${LG.utils.escapeHtml(segment.message || segment.reason || '')}</td>
        </tr>
      `;
    }).join('');

    $chainSegmentsBody.html(rows);
    $chainSegmentsWrap.removeClass('d-none');
  }

  /**
   * Verify the hash-chained audit ledger by segment.
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
        renderChainSegments(segments, res.active_segment);

        if (res.is_valid && archivedInvalid.length === 0) {
          setPosture($postureAudit, 'ok', '<i class="bi bi-check-circle-fill me-1"></i>Active segment verified');
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
          setPosture($postureAudit, 'warn', '<i class="bi bi-exclamation-triangle-fill me-1"></i>Active valid · archived invalid disclosed');
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
          setPosture($postureAudit, 'bad', '<i class="bi bi-x-octagon-fill me-1"></i>Active audit segment invalid');
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
      .fail(function (xhr) {
        renderChainSegments([], null);
        setPosture($postureAudit, 'bad', '<i class="bi bi-x-octagon-fill me-1"></i>Verification request failed');
        $chainStatusBanner.removeClass('alert-dark alert-success alert-warning').addClass('alert-danger')
          .text(apiErrorMessage(xhr, 'Failed to execute cryptographic verification.'));
      });
  });

  function syncResealSubmitState() {
    const reasonReady = ($('#reseal-reason').val() || '').trim().length >= 10;
    const confirmed = $('#reseal-confirm').is(':checked');
    $('#reseal-submit-btn').prop('disabled', !(reasonReady && confirmed));
  }

  $('#open-reseal-btn').on('click', function () {
    if (!$resealModal) return;
    $('#reseal-form')[0].reset();
    syncResealSubmitState();
    $resealModal.show();
  });
  $('#reseal-reason').on('input', syncResealSubmitState);
  $('#reseal-confirm').on('change', syncResealSubmitState);

  $('#reseal-form').on('submit', function (event) {
    event.preventDefault();
    const reason = $('#reseal-reason').val().trim();
    const $submit = $('#reseal-submit-btn').prop('disabled', true);

    LG.api.admin.resealAuditChain(reason)
      .done(function (res) {
        if ($resealModal) $resealModal.hide();
        $chainStatusBanner.removeClass('d-none alert-dark alert-danger alert-warning').addClass('alert-success')
          .html(
            '<strong>Audit chain resealed.</strong> Active segment is now ' +
            LG.utils.escapeHtml(res.segment) +
            '; genesis hash ' +
            LG.utils.escapeHtml(LG.utils.truncateHash(res.current_hash, 8)) +
            '. Historical rows were retained unchanged.'
          );
        LG.toast('Audit chain resealed into a new disclosed segment.', 'success');
        loadAuditLogs();
        loadAnalytics();
        $verifyChainBtn.trigger('click');
      })
      .fail(function (xhr) {
        LG.toast(apiErrorMessage(xhr, 'Failed to reseal audit chain.'), 'danger');
      })
      .always(function () {
        syncResealSubmitState();
        if (!$('#reseal-reason').val()) $submit.prop('disabled', true);
      });
  });

  // Refresh Button
  $refreshBtn.on('click', function () {
    loadAnalytics();
    loadApprovalQueue();
    loadAuditLogs();
    loadSystemReadiness();
    if (isSeniorAdmin && usersLoaded) loadUsers();
    LG.toast('Workstation data refreshed.', 'info');
  });

  // Initial Load
  loadAnalytics();
  loadApprovalQueue();
  loadAuditLogs();
  loadSystemReadiness();
});
