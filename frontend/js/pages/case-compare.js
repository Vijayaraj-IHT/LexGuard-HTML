/**
 * LexGuard — Multi-Precedent Comparator Controller (case-compare.js)
 * Semester 5 Project · LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  const $targetSelect = $('#select-target-case');
  const $p1Select = $('#select-precedent-1');
  const $p2Select = $('#select-precedent-2');
  const $p3Select = $('#select-precedent-3');
  const $compareBtn = $('#run-compare-btn');
  const $swapBtn = $('#swap-cases-btn');
  const $printBtn = $('#print-report-btn');

  const $loading = $('#compare-loading');
  const $resultsContainer = $('#compare-results-container');
  const $bestTitle = $('#best-match-title');
  const $bestDesc = $('#best-match-desc');
  const $scoreRingCircle = $('#score-ring-circle');
  const $scoreRingText = $('#score-ring-text');
  const $scorePills = $('#precedent-score-pills');
  const $matrixHeadRow = $('#matrix-head-row');
  const $matrixBody = $('#matrix-table-body');

  let precedentsCache = {};

  /**
   * Load precedents from API into all 4 selection dropdowns.
   */
  function loadPrecedents() {
    LG.api.comparison.getPrecedents()
      .done(function (precedents) {
        let targetOpts = '<option value="">Choose Target Case...</option>';
        let p1Opts = '<option value="">Choose Precedent 1...</option>';
        let p2Opts = '<option value="">Choose Precedent 2...</option>';
        let p3Opts = '<option value="">Choose Precedent 3 (Optional)...</option>';

        (precedents || []).forEach(function (p) {
          precedentsCache[p.id] = p;
          const label = `${p.title} (${p.court}, ${p.year})`;
          targetOpts += `<option value="${p.id}">${LG.utils.escapeHtml(label)}</option>`;
          p1Opts += `<option value="${p.id}">${LG.utils.escapeHtml(label)}</option>`;
          p2Opts += `<option value="${p.id}">${LG.utils.escapeHtml(label)}</option>`;
          p3Opts += `<option value="${p.id}">${LG.utils.escapeHtml(label)}</option>`;
        });

        $targetSelect.html(targetOpts);
        $p1Select.html(p1Opts);
        $p2Select.html(p2Opts);
        $p3Select.html(p3Opts);

        // Check URL parameters ?case1=...&case2=...
        const param1 = LG.utils.getQueryParam('case1');
        const param2 = LG.utils.getQueryParam('case2');

        if (param1) $targetSelect.val(param1);
        if (param2) $p1Select.val(param2);

        // Pre-populate sensible defaults if empty
        if (precedents && precedents.length >= 3) {
          if (!$targetSelect.val()) $targetSelect.val(precedents[0].id);
          if (!$p1Select.val()) $p1Select.val(precedents[1].id);
          if (!$p2Select.val()) $p2Select.val(precedents[2].id);
        }

        if ($targetSelect.val() && $p1Select.val()) {
          runMultiComparison();
        }
      })
      .fail(function () {
        LG.toast('Failed to load published precedents for comparator tray.', 'danger');
      });
  }

  /**
   * Run Multi-Precedent Comparison using /comparison/compare-multi.
   */
  function runMultiComparison() {
    const targetId = $targetSelect.val();
    const p1Id = $p1Select.val();
    const p2Id = $p2Select.val();
    const p3Id = $p3Select.val();

    if (!targetId || !p1Id) {
      LG.toast('Please select at least a target case and one comparison precedent.', 'warning');
      return;
    }

    const selectedPrecedentIds = [p1Id, p2Id, p3Id].filter(Boolean);
    const target = precedentsCache[targetId] || {};

    $loading.removeClass('d-none');
    $resultsContainer.addClass('d-none');

    const payload = {
      precedent_case_ids: selectedPrecedentIds,
      case_title: target.title || 'Target Petition',
      court_jurisdiction: target.court || 'High Court of Judicature',
      facts_summary: target.summary || target.ratio_decidendi || 'Dispute regarding procedural compliance and statutory bar.',
      statutory_provisions: (target.section_tags || target.sections || []).length > 0 ? (target.section_tags || target.sections) : ['Section 482 CrPC'],
      legal_issues: [target.ratio_decidendi || 'Applicability of binding judicial precedent']
    };

    LG.api.request({
      url: '/comparison/compare-multi',
      method: 'POST',
      data: payload
    })
      .done(function (res) {
        renderMultiResults(res, target, selectedPrecedentIds);
      })
      .fail(function (xhr) {
        let msg = 'Failed to execute multi-case comparison.';
        if (xhr.responseJSON && xhr.responseJSON.detail) {
          msg = typeof xhr.responseJSON.detail === 'string'
            ? xhr.responseJSON.detail
            : JSON.stringify(xhr.responseJSON.detail);
        }
        LG.toast(msg, 'danger');
      })
      .always(function () {
        $loading.addClass('d-none');
      });
  }

  /**
   * Render Multi-Comparison Table and SVG score gauges.
   */
  function renderMultiResults(res, target, precedentIds) {
    $resultsContainer.removeClass('d-none');

    const results = res.results || [];
    if (results.length === 0) {
      LG.toast('No comparison results generated.', 'warning');
      return;
    }

    // 1. Best Match Header
    const bestScore = Math.round(res.best_match_score || 0);
    const circumference = 220;
    const offset = circumference - (bestScore / 100) * circumference;
    $scoreRingCircle.css('stroke-dashoffset', offset);
    $scoreRingText.text(bestScore + '%');

    // Find best precedent object
    const bestPrecedent = precedentsCache[res.best_match_id] || results[0].precedent || {};
    $bestTitle.text(bestPrecedent.title || 'Landmark Precedent');
    $bestDesc.text(`Highest dimensional score (${bestScore}%) based on statutory overlap, bench hierarchy, and remedy congruence.`);

    // 2. Score Pills across evaluated authorities
    const pillsHtml = results.map(function (item, idx) {
      const p = item.precedent || {};
      const score = Math.round(item.overall_score || 0);
      return `
        <div class="p-2 px-3 rounded bg-dark border border-secondary border-opacity-25 small mb-1">
          <div class="fw-bold text-light">${LG.utils.escapeHtml(p.title || `Precedent ${idx + 1}`)}</div>
          <div class="d-flex align-items-center gap-2 mt-1">
            <span class="badge ${score >= 70 ? 'bg-success' : 'badge-gold'} font-mono">${score}% Alignment</span>
            <span class="text-secondary" style="font-size: 0.75rem;">${p.court || ''}</span>
          </div>
        </div>
      `;
    }).join('');
    $scorePills.html(pillsHtml);

    // 3. Multi-Column Header Row
    let headHtml = `
      <th style="width: 25%;">Dimension</th>
      <th style="width: 25%;">Target Petition Value</th>
    `;
    const colWidth = Math.floor(50 / results.length);

    results.forEach(function (r, idx) {
      const p = r.precedent || {};
      headHtml += `
        <th style="width: ${colWidth}%;">
          <div class="text-warning">${LG.utils.escapeHtml(p.title || `Precedent ${idx + 1}`)}</div>
          <span class="badge ${Math.round(r.overall_score) >= 70 ? 'bg-success' : 'badge-gold'} mt-1 font-mono">${Math.round(r.overall_score)}%</span>
        </th>
      `;
    });
    $matrixHeadRow.html(headHtml);

    // 4. Matrix Rows by Dimension
    const baseDimensions = (results[0].dimensions || []);
    let bodyHtml = '';

    baseDimensions.forEach(function (baseDim, dIdx) {
      bodyHtml += `
        <tr>
          <td>
            <div class="fw-bold text-light">${LG.utils.escapeHtml(baseDim.dimension_name)}</div>
            <div class="text-secondary small mt-1" style="font-size: 0.76rem;">${LG.utils.escapeHtml(baseDim.explanation || '')}</div>
          </td>
          <td class="font-mono text-light small">${LG.utils.escapeHtml(baseDim.user_value || '—')}</td>
      `;

      // Render column for each precedent
      results.forEach(function (r) {
        const dim = (r.dimensions || [])[dIdx] || {};
        let stateBadge = 'badge bg-secondary';
        if (dim.match_state === 'exact') stateBadge = 'badge bg-success';
        else if (dim.match_state === 'partial') stateBadge = 'badge badge-gold';
        else if (dim.match_state === 'different') stateBadge = 'badge bg-danger';

        const dScore = Math.round(dim.dimension_score || 0);

        bodyHtml += `
          <td>
            <div class="d-flex align-items-center justify-content-between mb-1">
              <span class="${stateBadge}">${LG.utils.escapeHtml(dim.match_state || 'N/A')}</span>
              <span class="small font-mono fw-bold text-light">${dScore}%</span>
            </div>
            <div class="progress mb-2" style="height: 4px; background-color: #0c1019;">
              <div class="progress-bar ${dScore >= 70 ? 'bg-success' : 'bg-warning'}" style="width: ${dScore}%;"></div>
            </div>
            <div class="font-mono text-secondary small" style="font-size: 0.78rem;">${LG.utils.escapeHtml(dim.precedent_value || '—')}</div>
          </td>
        `;
      });

      bodyHtml += `</tr>`;
    });

    $matrixBody.html(bodyHtml);
  }

  // Event Handlers
  $compareBtn.on('click', runMultiComparison);

  $swapBtn.on('click', function () {
    const val1 = $p1Select.val();
    const val2 = $p2Select.val();
    $p1Select.val(val2);
    $p2Select.val(val1);
    runMultiComparison();
  });

  $printBtn.on('click', function () {
    window.print();
  });

  // Export Modal Handlers
  const compExportModal = new bootstrap.Modal(document.getElementById('comparisonExportModal'));

  $('#export-comparison-btn').on('click', function () {
    compExportModal.show();
  });

  $('#export-csv-btn').on('click', function () {
    if (!currentMultiData || !currentMultiData.results) {
      LG.toast('Run a comparison first before exporting.', 'warning');
      return;
    }
    const headers = ['Dimension', 'Target Case'];
    currentMultiData.results.forEach(r => headers.push(r.precedent_case_no || r.precedent_id));
    let csv = headers.map(h => `"${h}"`).join(',') + '\n';

    DIMENSION_KEYS.forEach(function (d, dIdx) {
      const row = [d.name, (currentMultiData.target_case && currentMultiData.target_case[d.key]) || 'N/A'];
      currentMultiData.results.forEach(function (r) {
        const dim = (r.dimensions || [])[dIdx] || {};
        row.push(`${dim.match_state || 'N/A'} (${Math.round(dim.dimension_score || 0)}%)`);
      });
      csv += row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',') + '\n';
    });

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `precedent_comparison_${Date.now()}.csv`;
    link.click();
    LG.toast('CSV matrix downloaded successfully!', 'success');
    compExportModal.hide();
  });

  $('#export-md-btn').on('click', function () {
    if (!currentMultiData || !currentMultiData.results) {
      LG.toast('Run a comparison first before exporting.', 'warning');
      return;
    }
    let md = `| Dimension | Target Case | ` + currentMultiData.results.map(r => r.precedent_case_no || r.precedent_id).join(' | ') + ` |\n`;
    md += `| --- | --- | ` + currentMultiData.results.map(() => `---`).join(' | ') + ` |\n`;

    DIMENSION_KEYS.forEach(function (d, dIdx) {
      md += `| **${d.name}** | ` + ((currentMultiData.target_case && currentMultiData.target_case[d.key]) || 'N/A') + ` | `;
      md += currentMultiData.results.map(r => {
        const dim = (r.dimensions || [])[dIdx] || {};
        return `${dim.match_state} (${Math.round(dim.dimension_score || 0)}%)`;
      }).join(' | ') + ` |\n`;
    });

    LG.utils.copyToClipboard(md, 'Markdown comparative matrix copied to clipboard!');
    compExportModal.hide();
  });

  $('#export-print-btn').on('click', function () {
    compExportModal.hide();
    window.print();
  });

  // Initial Load
  loadPrecedents();
});
