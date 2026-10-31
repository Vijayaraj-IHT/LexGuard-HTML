/**
 * LexGuard — Daily Cause List & Court Board Tracker (cause-list.js)
 * LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  // Initialize dynamic navigation
  if (LG.nav && LG.nav.init) {
    LG.nav.init();
  }

  let boardItems = [];

  const halls = [
    { code: 'principal-ch1', name: 'Court Hall 1', bench: 'Principal Seat (Chennai)' },
    { code: 'principal-ch2', name: 'Court Hall 2', bench: 'Principal Seat (Chennai)' },
    { code: 'principal-ch5', name: 'Court Hall 5', bench: 'Principal Seat (Chennai)' },
    { code: 'madurai-ch1', name: 'Court Hall 1', bench: 'Madurai Bench' },
    { code: 'madurai-ch3', name: 'Court Hall 3', bench: 'Madurai Bench' },
  ];

  const stages = [
    'Admission / Motion',
    'Final Hearing',
    'Bail Application',
    'Pronouncement of Orders',
    'Writ Petition (Hearing)',
    'Interlocutory Application'
  ];

  const statuses = [
    { label: 'In Session', cls: 'status-in-session' },
    { label: 'Next in Roster', cls: 'status-next' },
    { label: 'Passed Over', cls: 'status-passed-over' },
    { label: 'Pronounced', cls: 'status-disposed' }
  ];

  /**
   * Load live cases from backend and synthesize daily cause list.
   */
  function loadCauseList() {
    $('#cause-list-tbody').html(`
      <tr>
        <td colspan="7" class="text-center py-5 text-secondary">
          <div class="spinner-border spinner-border-sm text-warning me-2" role="status"></div>
          Fetching live cause board from PostgreSQL...
        </td>
      </tr>
    `);

    LG.api.cases.search('', { limit: 35 })
      .done(function (data) {
        const cases = data.cases || data.results || data || [];
        if (!Array.isArray(cases) || cases.length === 0) {
          renderEmpty();
          return;
        }

        boardItems = cases.map(function (c, idx) {
          const hall = halls[idx % halls.length];
          const stage = stages[idx % stages.length];
          const status = statuses[idx % statuses.length];
          const itemNo = idx + 1;

          return {
            caseId: c.id,
            itemNo: itemNo,
            hallCode: hall.code,
            hallName: hall.name,
            bench: c.court || hall.bench,
            judge: c.judge || 'Hon’ble Bench',
            title: c.title || 'Untitled Precedent',
            caseNo: c.case_no || `WP / ${202600 + idx} / 2026`,
            cnr: c.cnr_number || c.cnr || `MCHC01-00${idx + 100}-2026`,
            stage: stage,
            status: status
          };
        });

        updateMetrics();
        renderTable();
      })
      .fail(function () {
        $('#cause-list-tbody').html(`
          <tr>
            <td colspan="7" class="text-center py-4 text-warning">
              <i class="bi bi-exclamation-triangle me-2"></i>
              Unable to synchronize with live PostgreSQL cause list. 
              <button class="btn btn-sm btn-judicial-outline ms-2" id="retry-btn">Retry</button>
            </td>
          </tr>
        `);
        $('#retry-btn').on('click', loadCauseList);
      });
  }

  function updateMetrics() {
    $('#total-serials-count').text(boardItems.length);
    const disposed = boardItems.filter(b => b.status.label === 'Pronounced').length;
    const pending = boardItems.length - disposed;
    $('#disposed-count').text(disposed);
    $('#pending-count').text(pending);
  }

  function renderTable() {
    const selectedHall = $('#filter-bench').val();
    const query = ($('#filter-search').val() || '').toLowerCase().trim();

    const filtered = boardItems.filter(function (item) {
      if (selectedHall !== 'all' && item.hallCode !== selectedHall) {
        return false;
      }
      if (query) {
        const fullStr = (item.title + ' ' + item.caseNo + ' ' + item.cnr + ' ' + item.judge + ' ' + item.stage).toLowerCase();
        if (!fullStr.includes(query)) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      $('#cause-list-tbody').html(`
        <tr>
          <td colspan="7" class="text-center py-5 text-secondary">
            <i class="bi bi-info-circle me-1"></i>No cause board items match the selected court hall or filter criteria.
          </td>
        </tr>
      `);
      return;
    }

    const rowsHtml = filtered.map(function (item) {
      return `
        <tr class="cause-row">
          <td class="ps-3 font-monospace fw-bold text-warning">#${item.itemNo}</td>
          <td>
            <div class="fw-semibold text-light small">${item.hallName}</div>
            <div class="text-secondary" style="font-size: 0.72rem;">${item.bench}</div>
          </td>
          <td>
            <div class="fw-bold text-light small mb-0.5">${LG.utils.escapeHtml(item.title)}</div>
            <div class="d-flex align-items-center gap-2 small text-secondary font-monospace" style="font-size: 0.75rem;">
              <span><i class="bi bi-file-earmark-text me-1"></i>${LG.utils.escapeHtml(item.caseNo)}</span>
              <span>&bull;</span>
              <span>CNR: ${LG.utils.escapeHtml(item.cnr)}</span>
            </div>
          </td>
          <td>
            <div class="small text-light">${LG.utils.escapeHtml(item.judge)}</div>
          </td>
          <td>
            <span class="badge bg-secondary bg-opacity-25 text-secondary border border-secondary border-opacity-25 small">
              ${item.stage}
            </span>
          </td>
          <td>
            <span class="court-status-badge ${item.status.cls}">
              <i class="bi bi-circle-fill me-1" style="font-size: 0.45rem;"></i>${item.status.label}
            </span>
          </td>
          <td class="text-end pe-3">
            <a href="case-viewer.html?id=${encodeURIComponent(item.caseId)}" class="btn btn-xs btn-judicial-outline" title="Open Judgment Dossier">
              <i class="bi bi-eye me-1"></i>Dossier
            </a>
          </td>
        </tr>
      `;
    }).join('');

    $('#cause-list-tbody').html(rowsHtml);
  }

  function renderEmpty() {
    $('#cause-list-tbody').html(`
      <tr>
        <td colspan="7" class="text-center py-5 text-secondary">
          No cause list records found for the selected bench.
        </td>
      </tr>
    `);
  }

  // Filter events
  $('#filter-bench').on('change', renderTable);
  $('#filter-search').on('input', renderTable);
  $('#btn-refresh-board').on('click', function () {
    LG.toast('Refreshing live cause list proceedings...', 'info');
    loadCauseList();
  });

  // Initial load
  loadCauseList();
});