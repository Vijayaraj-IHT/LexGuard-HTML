import os
import re

html_files = [
    r"e:\SEM 5 PROJECT\Lexguard\lexguard-html\case-viewer.html",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend\case-viewer.html",
]

js_case_viewer_files = [
    r"e:\SEM 5 PROJECT\Lexguard\lexguard-html\js\pages\case-viewer.js",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend\js\pages\case-viewer.js",
]

js_search_files = [
    r"e:\SEM 5 PROJECT\Lexguard\lexguard-html\js\pages\search.js",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend\js\pages\search.js",
]

# 1. Update case-viewer.html header badge
HEADER_BADGES = """          <div class="d-flex align-items-center gap-2">
            <span class="badge bg-success bg-opacity-25 text-success border border-success border-opacity-30 fs-7" id="case-header-status-badge">
              <i class="bi bi-shield-check me-1"></i>Precedential status not checked
            </span>
            <span class="badge bg-warning bg-opacity-20 text-warning border border-warning border-opacity-30 fs-7 d-none" id="case-header-cited-count-badge">
              <i class="bi bi-diagram-3 me-1"></i><span id="case-header-cited-count-text">0 Citations</span>
            </span>
            <span class="badge badge-gold fs-6" id="case-header-outcome">—</span>
          </div>"""

for hp in html_files:
    if not os.path.exists(hp):
        continue
    with open(hp, "r", encoding="utf-8") as f:
        content = f.read()

    outcome_pattern = re.compile(r'<div>\s*<span\s+class="badge badge-gold fs-6"\s+id="case-header-outcome">.*?</span>\s*</div>', re.DOTALL)
    if outcome_pattern.search(content):
        content = outcome_pattern.sub(HEADER_BADGES, content)
        print(f"Updated header badges in {hp}")

    with open(hp, "w", encoding="utf-8") as f:
        f.write(content)

# 2. Update case-viewer.js
NEW_LOAD_PRECEDENTS = """  function loadPrecedentNetwork(cid) {
    const apiBase = (window.LexGuard && window.LexGuard.API_BASE_URL) || window.API_BASE_URL || 'http://127.0.0.1:8000/api/v1';
    $.ajax({
      url: apiBase + '/cases/' + encodeURIComponent(cid) + '/citations',
      type: 'GET',
      xhrFields: { withCredentials: true },
      success: function (res) {
        if (!res) return;
        const precedentsCited = res.precedents_cited || [];
        const citedBy = res.cited_by || [];

        let html = `
          <div class="row g-3 mb-4">
            <div class="col-sm-4">
              <div class="p-3 rounded bg-dark border border-success border-opacity-30">
                <div class="text-secondary small text-uppercase">Precedential Authority</div>
                <div class="fw-bold text-success fs-6 mt-1">
                  <i class="bi bi-shield-check me-1"></i>${LG.utils.escapeHtml(res.precedential_status || 'Precedential status not checked')}
                </div>
              </div>
            </div>
            <div class="col-sm-4">
              <div class="p-3 rounded bg-dark border border-secondary border-opacity-30">
                <div class="text-secondary small text-uppercase">Official Law Report Citation</div>
                <div class="fw-bold font-mono text-warning fs-6 mt-1">
                  ${LG.utils.escapeHtml(res.official_citation || 'LexGuard Certified Precedent')}
                </div>
              </div>
            </div>
            <div class="col-sm-4">
              <div class="p-3 rounded bg-dark border border-warning border-opacity-30">
                <div class="text-secondary small text-uppercase">Downstream Citations ("Cited In")</div>
                <div class="fw-bold text-warning fs-6 mt-1">
                  <i class="bi bi-diagram-3 me-1"></i>Cited by ${citedBy.length} ${citedBy.length === 1 ? 'Judgment' : 'Judgments'}
                </div>
              </div>
            </div>
          </div>
        `;

        // Section 1: Precedents Cited in this judgment
        html += `
          <div class="mb-4">
            <h6 class="fw-bold text-light text-uppercase border-bottom border-secondary border-opacity-25 pb-2 mb-3">
              <i class="bi bi-arrow-up-right-circle text-info me-2"></i>Authorities &amp; Precedents Cited in this Judgment (${precedentsCited.length})
            </h6>
        `;

        if (precedentsCited.length === 0) {
          html += `
            <div class="text-secondary small p-3 text-center border border-secondary border-opacity-15 rounded bg-dark bg-opacity-25">
              <i class="bi bi-info-circle me-1"></i>No upstream formal judicial citations explicitly extracted for this judgment.
            </div>
          `;
        } else {
          html += '<div class="row g-2">';
          precedentsCited.forEach(function (p) {
            const hasDbCase = !!p.case_id;
            const targetUrl = hasDbCase ? `case-viewer.html?id=${encodeURIComponent(p.case_id)}` : `search.html?q=${encodeURIComponent(p.citation || p.title)}`;
            html += `
              <div class="col-md-6">
                <div class="card card-judicial p-3 h-100 border-secondary border-opacity-30">
                  <div class="d-flex align-items-start justify-content-between gap-2 mb-1">
                    <span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-30" style="font-size: 0.72rem;">
                      <i class="bi bi-check-circle me-1"></i>${LG.utils.escapeHtml(p.status || 'Precedential status not checked')}
                    </span>
                    <span class="badge bg-dark border border-secondary text-warning font-mono" style="font-size: 0.72rem;">
                      ${LG.utils.escapeHtml(p.citation || 'Precedent')}
                    </span>
                  </div>
                  <div class="fw-bold text-light fs-7 my-1">
                    ${LG.utils.escapeHtml(p.title || 'Judicial Precedent')}
                  </div>
                  <div class="small text-secondary mb-2" style="font-size: 0.75rem;">
                    <i class="bi bi-building me-1"></i>${LG.utils.escapeHtml(p.court || 'Court')} &bull;
                    <span class="text-info">${LG.utils.escapeHtml(p.treatment || 'Relied upon')}</span>
                  </div>
                  <div class="mt-auto pt-2">
                    <a href="${targetUrl}" class="btn btn-xs ${hasDbCase ? 'btn-gold' : 'btn-judicial-outline'}">
                      <i class="bi ${hasDbCase ? 'bi-box-arrow-up-right' : 'bi-search'} me-1"></i>
                      ${hasDbCase ? 'View in LexGuard' : 'Search Case Law'}
                    </a>
                  </div>
                </div>
              </div>
            `;
          });
          html += '</div>';
        }
        html += '</div>';

        // Section 2: Judgments in LexGuard that Cite This Case ("Cited In")
        html += `
          <div>
            <h6 class="fw-bold text-light text-uppercase border-bottom border-secondary border-opacity-25 pb-2 mb-3">
              <i class="bi bi-arrow-down-left-circle text-warning me-2"></i>Repository Judgments Citing this Ruling ("Cited In") (${citedBy.length})
            </h6>
        `;

        if (citedBy.length === 0) {
          html += `
            <div class="text-secondary small p-3 text-center border border-secondary border-opacity-15 rounded bg-dark bg-opacity-25">
              <i class="bi bi-info-circle me-1"></i>No downstream judgments in the current repository subset cite this ruling yet.
            </div>
          `;
        } else {
          html += '<div class="d-flex flex-column gap-2">';
          citedBy.forEach(function (cb) {
            html += `
              <div class="card card-judicial p-3 border-warning border-opacity-25">
                <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
                  <div>
                    <a href="case-viewer.html?id=${encodeURIComponent(cb.id)}" class="fw-bold text-light text-decoration-none">
                      ${LG.utils.escapeHtml(cb.title || cb.case_no)}
                    </a>
                    <div class="small text-secondary mt-1">
                      <span class="${LG.utils.courtBadgeClass(cb.court)} me-2">${LG.utils.escapeHtml(cb.court || '')}</span>
                      <span class="badge bg-secondary me-2">${cb.year || '—'}</span>
                      <span class="badge badge-gold me-2">${LG.utils.escapeHtml(cb.outcome || 'Decided')}</span>
                      <span class="font-mono text-light">${LG.utils.escapeHtml(cb.case_no || '')}</span>
                    </div>
                  </div>
                  <div class="d-flex align-items-center gap-2">
                    <a href="case-viewer.html?id=${encodeURIComponent(cb.id)}" class="btn btn-xs btn-gold">
                      <i class="bi bi-eye me-1"></i>View Judgment
                    </a>
                    <a href="case-compare.html?case1=${encodeURIComponent(cid)}&case2=${encodeURIComponent(cb.id)}" class="btn btn-xs btn-judicial-outline">
                      <i class="bi bi-columns-gap me-1"></i>Compare
                    </a>
                  </div>
                </div>
              </div>
            `;
          });
          html += '</div>';
        }
        html += '</div>';

        $('#precedents-list').html(html);
      },
      error: function () {
        $('#precedents-list').html(`
          <div class="text-secondary small p-3 text-center">
            Unable to load precedent network at this time.
          </div>
        `);
      }
    });
  }"""

HEADER_UPDATE_LOGIC = """    if (c.precedential_status) {
      $('#case-header-status-badge').html(`<i class="bi bi-shield-check me-1"></i>${LG.utils.escapeHtml(c.precedential_status)}`).show();
    }
    if (c.cited_by_count && c.cited_by_count > 0) {
      $('#case-header-cited-count-text').text(`${c.cited_by_count} Citations`);
      $('#case-header-cited-count-badge').removeClass('d-none');
    } else {
      $('#case-header-cited-count-badge').addClass('d-none');
    }"""

for jp in js_case_viewer_files:
    if not os.path.exists(jp):
        continue
    with open(jp, "r", encoding="utf-8") as f:
        js = f.read()

    # Update header badges in renderCaseHeader
    if "case-header-status-badge" not in js:
        target = "$headerCaseno.html("
        if target in js:
            js = js.replace(target, HEADER_UPDATE_LOGIC + "\n    " + target)
            print(f"Added header badge logic in {jp}")

    # Replace loadPrecedentNetwork
    fn_pattern = re.compile(r'function loadPrecedentNetwork\(cid\)\s*\{.*?\}\s*(?=/\*|const|\Z)', re.DOTALL)
    if fn_pattern.search(js):
        js = fn_pattern.sub(NEW_LOAD_PRECEDENTS + "\n\n", js)
        print(f"Updated loadPrecedentNetwork in {jp}")

    with open(jp, "w", encoding="utf-8") as f:
        f.write(js)

# 3. Update search.js with Precedent badges & Citation Counts
SEARCH_BADGES = """                <span class="${courtBadge}">${LG.utils.escapeHtml(item.court)}</span>
                ${item.case_type ? `<span class="badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25">${LG.utils.escapeHtml(item.case_type)}</span>` : ''}
                <span class="badge bg-secondary">${item.year}</span>
                ${item.outcome ? `<span class="badge badge-gold">${LG.utils.escapeHtml(item.outcome)}</span>` : ''}
                ${item.precedential_status ? `<span class="badge bg-success bg-opacity-15 text-success border border-success border-opacity-30" style="font-size: 0.72rem;"><i class="bi bi-shield-check me-1"></i>${LG.utils.escapeHtml(item.precedential_status)}</span>` : ''}
                ${item.cited_by_count > 0 ? `<span class="badge bg-warning bg-opacity-15 text-warning border border-warning border-opacity-30" style="font-size: 0.72rem;"><i class="bi bi-diagram-3 me-1"></i>Cited in ${item.cited_by_count}</span>` : ''}
                ${item.official_citation ? `<span class="badge bg-dark text-warning border border-secondary border-opacity-25 font-mono" style="font-size: 0.7rem;">${LG.utils.escapeHtml(item.official_citation)}</span>` : ''}
                ${item.cnr_number ? `<span class="badge bg-dark text-light font-mono border border-secondary border-opacity-25" style="font-size: 0.7rem;"><i class="bi bi-upc-scan me-1"></i>${LG.utils.escapeHtml(item.cnr_number)}</span>` : ''}
                ${item.judge ? `<span class="small text-secondary"><i class="bi bi-person-fill me-1"></i>${LG.utils.escapeHtml(item.judge)}</span>` : ''}"""

for sp in js_search_files:
    if not os.path.exists(sp):
        continue
    with open(sp, "r", encoding="utf-8") as f:
        sjs = f.read()

    old_badges_pattern = re.compile(r'<span class="\$\{courtBadge\}">.*?</span>\s*\$\{item\.case_type.*?\$\{item\.judge.*?\</span>` : \'\'\}', re.DOTALL)
    if old_badges_pattern.search(sjs):
        sjs = old_badges_pattern.sub(SEARCH_BADGES, sjs)
        print(f"Updated search badges in {sp}")

    with open(sp, "w", encoding="utf-8") as f:
        f.write(sjs)

print("Precedent UI updates complete.")
