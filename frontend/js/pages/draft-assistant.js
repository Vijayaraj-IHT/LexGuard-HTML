/**
 * LexGuard — AI Draft Assistant & Precedent Audit Controller (draft-assistant.js)
 * LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  // Role validation: Requires Advocate, Scholar, or Court Staff
  if (!LG.session.isAuthenticated()) {
    LG.toast('Draft Assistant requires an Advocate or Legal Scholar account. Please sign in.', 'warning');
    setTimeout(function () {
      window.location.href = 'login.html?redirect=' + encodeURIComponent('draft-assistant.html');
    }, 1200);
    return;
  }

  const $editor = $('#petition-editor');
  const $titleInput = $('#draft-title-input');
  const $wordCount = $('#word-count');
  const $charCount = $('#char-count');
  const $templateSelect = $('#template-select');
  const $analyzeBtn = $('#run-analyze-btn');
  const $loadSampleBtn = $('#load-sample-btn');

  // Sessions Elements
  const $saveSessionBtn = $('#save-session-btn');
  const $loadSessionsBtn = $('#load-sessions-btn');
  const $sessionsModal = new bootstrap.Modal(document.getElementById('sessionsModal'));
  const $sessionsList = $('#sessions-list');

  // Mode A: Gap Analysis
  const $emptyState = $('#analysis-empty-state');
  const $loading = $('#analysis-loading');
  const $results = $('#analysis-results');
  const $statusBadge = $('#analysis-status-badge');
  const $groundsList = $('#identified-grounds-list');
  const $missingList = $('#missing-arguments-list');
  const $sectionsBox = $('#suggested-sections-box');
  const $citationsList = $('#citations-list');
  const $disclaimer = $('#analysis-disclaimer');

  // Mode B: Benchmark Precision Precedent Audit
  const $benchmarkSelect = $('#benchmark-precedent-select');
  const $runBenchmarkBtn = $('#run-benchmark-btn');
  const $bmLoading = $('#benchmark-loading');
  const $bmResults = $('#benchmark-results');
  const $bmCaseTitle = $('#bm-case-title');
  const $bmCaseCitation = $('#bm-case-citation');
  const $bmCompliancePercent = $('#bm-compliance-percent');
  const $bmAuditChecklist = $('#bm-audit-checklist');
  const $bmBoilerplateList = $('#bm-boilerplate-list');

  // Sample Templates
  const templates = {
    quash: `IN THE HIGH COURT OF JUDICATURE AT MADRAS
(CRIMINAL MISCELLANEOUS JURISDICTION)

CRL. O.P. NO. 4521 OF 2026

BETWEEN:
K. Senthil Kumar,
S/o. Late Ramanathan,
Residing at No. 42, Anna Nagar West, Chennai - 600040.
                                                    ... Petitioner / Accused No. 1
                                    AND
1. State represented by
   The Inspector of Police,
   Central Crime Branch, Chennai.
   (Crime No. 128/2025)

2. M/s. Global Tech Solutions Pvt. Ltd.,
   Rep. by its Director, V. Anand.
                                                    ... Respondents / Complainants

PETITION UNDER SECTION 482 OF THE CODE OF CRIMINAL PROCEDURE, 1973

The Petitioner above-named states as follows:

1. The Petitioner is arrayed as Accused No. 1 in Crime No. 128 of 2025 on the file of the 1st Respondent Police for alleged offences punishable under Sections 406 and 420 of the Indian Penal Code, 1860.

2. It is respectfully submitted that the dispute between the Petitioner and the 2nd Respondent arises out of a commercial software service agreement dated 15.01.2023. The dispute is purely civil and contractual in nature regarding reconciliation of project milestone payments.

3. The allegations in the FIR, even if taken on their face value and accepted in their entirety, do not prima facie constitute any offence of cheating or criminal breach of trust. There is no fraudulent or dishonest intention at the inception of the transaction.

4. The criminal proceedings initiated by the 2nd Respondent are an abuse of process of the Court intended solely to exert unlawful pressure for commercial recovery.

PRAYER:
Wherefore, it is prayed that this Hon'ble Court may be pleased to call for the records in Crime No. 128 of 2025 on the file of the 1st Respondent Police and quash the same as against the Petitioner.`,

    bail: `IN THE HIGH COURT OF JUDICATURE AT MADRAS
(CRIMINAL ORIGINAL JURISDICTION)

CRL. O.P. NO. 7890 OF 2026

PETITION FOR ANTICIPATORY BAIL UNDER SECTION 438 OF Cr.P.C.

BETWEEN:
R. Rajesh Kumar                                     ... Petitioner / Accused
                                    AND
The State, rep. by Inspector of Police,
Cyber Crime Division, Chennai.                       ... Respondent / Prosecution

1. The Petitioner apprehends arrest at the hands of the Respondent Police in connection with an alleged enquiry relating to financial transactions.
2. The Petitioner is an innocent citizen having deep roots in the community and is ready to cooperate fully with the investigation.
3. Personal liberty guaranteed under Article 21 of the Constitution of India must be protected against arbitrary and unwarranted arrest.`,

    writ: `IN THE HIGH COURT OF JUDICATURE AT MADRAS
(EXTRAORDINARY ORIGINAL WRIT JURISDICTION)

W.P. NO. 11200 OF 2026

WRIT OF MANDAMUS UNDER ARTICLE 226 OF THE CONSTITUTION OF INDIA

1. The Petitioner challenges the arbitrary inaction of the Respondent Authorities in disposing of the statutory representation dated 12.02.2025.
2. The principles of natural justice and audi alteram partem have been violated.`
  };

  function updateCounters() {
    const text = $editor.val();
    const chars = text.length;
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    $charCount.text(chars);
    $wordCount.text(words);
  }

  $editor.on('input propertychange', updateCounters);

  $templateSelect.on('change', function () {
    const key = $(this).val();
    if (key && templates[key]) {
      $editor.val(templates[key]);
      updateCounters();
      LG.toast('Sample petition template loaded into editor.', 'info');
    }
  });

  $loadSampleBtn.on('click', function () {
    $templateSelect.val('quash').trigger('change');
  });

  /* -------------------------------------------------------------------------
     Session Management (Save & Load Drafts)
     ------------------------------------------------------------------------- */
  $saveSessionBtn.on('click', function () {
    const text = $editor.val().trim();
    const title = $titleInput.val().trim() || 'Untitled Petition Draft';

    if (!text) {
      LG.toast('Cannot save empty petition draft.', 'warning');
      return;
    }

    $saveSessionBtn.prop('disabled', true);

    LG.api.request({
      url: '/draft/sessions',
      method: 'POST',
      data: {
        title: title,
        draft_text: text
      }
    })
      .done(function () {
        LG.toast('Draft session saved to database!', 'success');
      })
      .fail(function () {
        LG.toast('Failed to save draft session.', 'danger');
      })
      .always(function () {
        $saveSessionBtn.prop('disabled', false);
      });
  });

  $loadSessionsBtn.on('click', function () {
    $sessionsModal.show();
    $sessionsList.html('<div class="text-center py-4 text-secondary"><div class="spinner-border spinner-border-sm text-warning me-2"></div>Loading saved sessions...</div>');

    LG.api.request({
      url: '/draft/sessions',
      method: 'GET'
    })
      .done(function (sessions) {
        if (!Array.isArray(sessions) || sessions.length === 0) {
          $sessionsList.html('<div class="text-secondary text-center py-4">No saved draft sessions found.</div>');
          return;
        }

        const itemsHtml = sessions.map(function (s) {
          return `
            <div class="card card-judicial p-3 session-item cursor-pointer" data-id="${s.id}" data-text="${LG.utils.escapeHtml(s.draft_text)}" data-title="${LG.utils.escapeHtml(s.title)}">
              <div class="d-flex align-items-center justify-content-between mb-1">
                <span class="fw-bold text-light">${LG.utils.escapeHtml(s.title)}</span>
                <span class="small text-secondary">${LG.utils.formatDateTime(s.updated_at || s.created_at)}</span>
              </div>
              <p class="small text-secondary mb-0 text-truncate" style="max-height: 40px;">${LG.utils.escapeHtml(s.draft_text.substring(0, 180))}...</p>
            </div>
          `;
        }).join('');

        $sessionsList.html(itemsHtml);

        $('.session-item').on('click', function () {
          const title = $(this).data('title');
          const text = $(this).data('text');
          $titleInput.val(title);
          $editor.val(text);
          updateCounters();
          $sessionsModal.hide();
          LG.toast(`Loaded session: "${title}"`, 'info');
        });
      })
      .fail(function () {
        $sessionsList.html('<div class="text-danger text-center py-4">Failed to fetch saved sessions.</div>');
      });
  });

  /* -------------------------------------------------------------------------
     Mode A: General AI Gap Analysis
     ------------------------------------------------------------------------- */
  function runGapAnalysis() {
    const petitionText = $editor.val().trim();
    if (petitionText.length < 20) {
      LG.toast('Please write or paste a petition draft (at least 20 characters).', 'warning');
      return;
    }

    $emptyState.addClass('d-none');
    $results.addClass('d-none');
    $loading.removeClass('d-none');
    $statusBadge.attr('class', 'badge badge-gold').text('Analyzing Grounds...');
    $analyzeBtn.prop('disabled', true);

    LG.api.request({
      url: '/draft/analyze',
      method: 'POST',
      data: {
        petition_text: petitionText,
        title: $titleInput.val().trim() || 'Draft Petition Analysis'
      }
    })
      .done(function (res) {
        $statusBadge.attr('class', 'badge bg-success').text('Analysis Complete');

        // 1. Identified Grounds
        const grounds = res.identified_grounds || [];
        if (grounds.length > 0) {
          $groundsList.html(grounds.map(g => `<li class="mb-1">${LG.utils.escapeHtml(g)}</li>`).join(''));
        } else {
          $groundsList.html('<li class="text-secondary">No strong primary statutory grounds clearly parsed.</li>');
        }

        // 2. Missing Arguments with Severity Badges
        const missing = res.missing_arguments || [];
        if (missing.length > 0) {
          $missingList.html(missing.map(function (m, idx) {
            let severityBadge = 'badge bg-danger me-2';
            let label = 'High Priority Gap';
            if (idx === 1) {
              severityBadge = 'badge badge-gold me-2';
              label = 'Recommended Ground';
            } else if (idx > 1) {
              severityBadge = 'badge bg-info text-dark me-2';
              label = 'Procedural Note';
            }
            return `<li class="mb-2"><span class="${severityBadge}">${label}</span>${LG.utils.escapeHtml(m)}</li>`;
          }).join(''));
        } else {
          $missingList.html('<li class="text-success">No critical procedural arguments omitted.</li>');
        }

        // 3. Suggested Sections
        const sections = res.suggested_sections || [];
        if (sections.length > 0) {
          $sectionsBox.html(sections.map(s => `<span class="badge bg-dark text-info border border-info border-opacity-30 me-1 mb-1 p-2">${LG.utils.escapeHtml(s)}</span>`).join(''));
        } else {
          $sectionsBox.html('<span class="text-secondary small">General provisions applicable.</span>');
        }

        // 4. Grounded Citations
        const citations = res.citation_suggestions || [];
        if (citations.length > 0) {
          const citHtml = citations.map(function (c) {
            return `
              <div class="card card-judicial p-3 border-secondary border-opacity-25">
                <div class="d-flex align-items-start justify-content-between gap-2 mb-2">
                  <div>
                    <h5 class="h6 fw-bold text-light mb-0">${LG.utils.escapeHtml(c.case_title)}</h5>
                    <div class="small text-warning font-mono">${LG.utils.escapeHtml(c.citation)}</div>
                  </div>
                  <a href="case-viewer.html?id=${encodeURIComponent(c.case_id)}" class="btn btn-xs btn-judicial-outline" target="_blank">
                    <i class="bi bi-box-arrow-up-right me-1"></i>View Case
                  </a>
                </div>

                <p class="small text-secondary mb-2 fst-italic">"${LG.utils.escapeHtml(c.quote || c.reasoning || '')}"</p>

                <div class="d-flex align-items-center justify-content-between pt-2 border-top border-secondary border-opacity-15">
                  <span class="badge bg-secondary small">${LG.utils.escapeHtml(c.relevant_section || 'Precedent')}</span>
                  <button type="button" class="btn btn-xs btn-gold insert-citation-btn" data-citation="${LG.utils.escapeHtml(c.citation)}" data-title="${LG.utils.escapeHtml(c.case_title)}">
                    <i class="bi bi-plus-lg me-1"></i>Insert at Cursor
                  </button>
                </div>
              </div>
            `;
          }).join('');
          $citationsList.html(citHtml);
        } else {
          $citationsList.html('<div class="text-secondary small">No specific precedent match found for this factual subset.</div>');
        }

        if (res.disclaimer) $disclaimer.text(res.disclaimer);

        $results.removeClass('d-none');
        LG.toast('AI Gap Analysis complete!', 'success');

        // Insert at cursor position
        $('.insert-citation-btn').on('click', function () {
          const title = $(this).data('title');
          const cit = $(this).data('citation');
          const insertText = `\nIn accordance with the authoritative ruling in ${title} (${cit}), the Hon'ble Court affirmed that continuation of proceedings without prima facie ingredients constitutes an abuse of process.\n`;

          const el = document.getElementById('petition-editor');
          const start = el.selectionStart || el.value.length;
          const end = el.selectionEnd || el.value.length;
          const text = el.value;
          el.value = text.substring(0, start) + insertText + text.substring(end);
          el.focus();
          el.setSelectionRange(start + insertText.length, start + insertText.length);
          updateCounters();
          LG.toast(`Inserted citation for "${title}" at cursor!`, 'success');
        });
      })
      .fail(function (xhr) {
        $statusBadge.attr('class', 'badge bg-danger').text('Analysis Failed');
        let msg = 'Failed to analyze draft petition.';
        if (xhr.responseJSON && xhr.responseJSON.detail) {
          msg = typeof xhr.responseJSON.detail === 'string'
            ? xhr.responseJSON.detail
            : JSON.stringify(xhr.responseJSON.detail);
        }
        LG.toast(msg, 'danger');
        $emptyState.removeClass('d-none');
      })
      .always(function () {
        $loading.addClass('d-none');
        $analyzeBtn.prop('disabled', false);
      });
  }

  $analyzeBtn.on('click', runGapAnalysis);

  /* -------------------------------------------------------------------------
     Mode B: Benchmark Precision Precedent Audit
     ------------------------------------------------------------------------- */
  function loadBenchmarkPrecedents() {
    LG.api.comparison.getPrecedents()
      .done(function (precedents) {
        let opts = '<option value="">Choose landmark precedent to audit against...</option>';
        (precedents || []).forEach(function (p) {
          opts += `<option value="${p.id}">${LG.utils.escapeHtml(p.title)} (${p.court}, ${p.year})</option>`;
        });
        $benchmarkSelect.html(opts);
      });
  }

  $runBenchmarkBtn.on('click', function () {
    const caseId = $benchmarkSelect.val();
    const text = $editor.val().trim();

    if (!caseId) {
      LG.toast('Please select a precedent to benchmark against.', 'warning');
      return;
    }
    if (text.length < 10) {
      LG.toast('Please write or paste draft petition text on left pane.', 'warning');
      return;
    }

    $bmLoading.removeClass('d-none');
    $bmResults.addClass('d-none');

    LG.api.request({
      url: '/draft/compare-with-precedent',
      method: 'POST',
      data: {
        draft_text: text,
        case_id: caseId
      }
    })
      .done(function (res) {
        $bmCaseTitle.text(res.case_title || 'Precedent Authority');
        $bmCaseCitation.text(res.citation || '');
        const compliance = Math.round(res.compliance_percentage || 0);
        $bmCompliancePercent.text(compliance + '%');

        // Render Statutory Checklist
        const checklist = res.statutory_audit || [];
        if (checklist.length > 0) {
          const checkHtml = checklist.map(function (item) {
            const isFulfilled = item.status === 'fulfilled';
            return `
              <div class="p-2 px-3 rounded bg-dark border ${isFulfilled ? 'border-success' : 'border-danger'} border-opacity-30 small">
                <div class="d-flex align-items-center justify-content-between mb-1">
                  <span class="fw-bold text-light">${LG.utils.escapeHtml(item.test)}</span>
                  <span class="badge ${isFulfilled ? 'bg-success' : 'bg-danger'}">${isFulfilled ? 'Fulfilled' : 'Omitted Ground'}</span>
                </div>
                ${item.matched_clause ? `<div class="text-success fst-italic" style="font-size: 0.78rem;">Matched: "${LG.utils.escapeHtml(item.matched_clause)}"</div>` : ''}
                ${item.recommendation ? `<div class="text-warning small mt-1"><i class="bi bi-lightbulb me-1"></i>${LG.utils.escapeHtml(item.recommendation)}</div>` : ''}
              </div>
            `;
          }).join('');
          $bmAuditChecklist.html(checkHtml);
        } else {
          $bmAuditChecklist.html('<div class="text-secondary small">No specific checklist tests parsed.</div>');
        }

        // Render Boilerplate suggestions
        const boilerplate = res.boilerplate_suggestions || [];
        if (boilerplate.length > 0) {
          const bpHtml = boilerplate.map(function (bp) {
            return `
              <div class="p-2 rounded bg-black border border-secondary border-opacity-25 small">
                <div class="fw-semibold text-warning mb-1">${LG.utils.escapeHtml(bp.title || 'Recommended Clause')}</div>
                <div class="text-secondary font-serif mb-2" style="font-size: 0.8rem;">${LG.utils.escapeHtml(bp.clause || bp)}</div>
                <button type="button" class="btn btn-xs btn-judicial-outline insert-bp-btn" data-clause="${LG.utils.escapeHtml(bp.clause || bp)}">
                  <i class="bi bi-plus-lg me-1"></i>Insert Clause
                </button>
              </div>
            `;
          }).join('');
          $bmBoilerplateList.html(bpHtml);
          $('#bm-boilerplate-card').removeClass('d-none');

          $('.insert-bp-btn').on('click', function () {
            const clause = $(this).data('clause');
            const el = document.getElementById('petition-editor');
            const start = el.selectionStart || el.value.length;
            el.value = el.value.substring(0, start) + '\n' + clause + '\n' + el.value.substring(start);
            updateCounters();
            LG.toast('Inserted boilerplate clause into draft.', 'success');
          });
        } else {
          $('#bm-boilerplate-card').addClass('d-none');
        }

        $bmResults.removeClass('d-none');
        LG.toast('Precedent precision audit complete!', 'success');
      })
      .fail(function () {
        LG.toast('Failed to run precedent audit.', 'danger');
      })
      .always(function () {
        $bmLoading.addClass('d-none');
      });
  });

  /* -------------------------------------------------------------------------
     Draggable Resizer Gutter
     ------------------------------------------------------------------------- */
  const $resizer = $('#draft-resizer-gutter');
  const $leftPane = $('#editor-left-pane');
  const $rightPane = $('#analysis-right-pane');
  const $splitWrap = $('#draft-split-container');
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

  // Init
  loadBenchmarkPrecedents();
  if (!$editor.val()) {
    $templateSelect.val('quash').trigger('change');
  }
});
