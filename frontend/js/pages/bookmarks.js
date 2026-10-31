/**
 * LexGuard — Advocate Research Binders & Bookmarks Controller (bookmarks.js)
 * LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  // Requires user authentication
  if (!LG.requireAuth()) {
    return;
  }

  const $container = $('#bookmarks-container');
  const $loading = $('#bookmarks-loading');
  const $empty = $('#bookmarks-empty');
  const $badgeCount = $('#bookmarks-count-badge');
  const $binderSelect = $('#binder-select');
  const $statusLabel = $('#binder-status-label');

  let currentBinder = 'all';
  let cachedBookmarks = [];
  let availableBinders = ['General Research'];

  /**
   * Load user's binders and populate binder selectors.
   */
  function loadBinders() {
    return LG.api.bookmarks.getBinders()
      .done(function (binders) {
        if (!Array.isArray(binders) || binders.length === 0) {
          availableBinders = ['General Research'];
        } else {
          availableBinders = binders.map(b => b.binder_name);
        }

        // Populate binder dropdown
        let selectHtml = `<option value="all">All Binders (All Saved Precedents)</option>`;
        availableBinders.forEach(function (name) {
          selectHtml += `<option value="${LG.utils.escapeHtml(name)}">${LG.utils.escapeHtml(name)}</option>`;
        });
        $binderSelect.html(selectHtml);
        $binderSelect.val(currentBinder);

        // Populate edit modal binder select
        let editSelectHtml = '';
        availableBinders.forEach(function (name) {
          editSelectHtml += `<option value="${LG.utils.escapeHtml(name)}">${LG.utils.escapeHtml(name)}</option>`;
        });
        $('#edit-bm-binder-select').html(editSelectHtml);
      });
  }

  /**
   * Load user's saved bookmarks.
   */
  function loadBookmarks() {
    $loading.removeClass('d-none');
    $container.addClass('d-none').empty();
    $empty.addClass('d-none');

    LG.api.bookmarks.list(currentBinder)
      .done(function (bookmarks) {
        cachedBookmarks = bookmarks || [];
        if (!Array.isArray(bookmarks) || bookmarks.length === 0) {
          $empty.removeClass('d-none');
          $badgeCount.text('0 Cases Saved');
          $statusLabel.text(currentBinder === 'all' ? 'No saved precedents found' : `Empty binder: ${currentBinder}`);
          return;
        }

        const countText = `${bookmarks.length} Case${bookmarks.length > 1 ? 's' : ''} Saved`;
        $badgeCount.text(countText);
        $statusLabel.text(currentBinder === 'all' ? `Viewing all ${bookmarks.length} authorities` : `Binder '${currentBinder}' (${bookmarks.length} cases)`);

        const html = bookmarks.map(function (b) {
          const c = b.case || {};
          const courtBadge = LG.utils.courtBadgeClass(c.court);
          const binderName = b.binder_name || 'General Research';
          const citation = c.official_citation || `${c.title || 'Case'}, (${c.year || ''}) ${c.court || ''}`;
          const precedentialStatus = c.precedential_status || 'Good Law';

          return `
            <div class="lg-case-card mb-3" id="bookmark-card-${b.id}">
              <div class="d-flex align-items-start justify-content-between gap-3 mb-2">
                <div>
                  <a href="case-viewer.html?id=${encodeURIComponent(c.id || b.case_id)}" class="case-title">
                    ${LG.utils.escapeHtml(c.title || 'Untitled Judgment')}
                  </a>
                  <div class="d-flex flex-wrap align-items-center gap-2 mt-1">
                    <span class="badge bg-dark border border-secondary text-warning">
                      <i class="bi bi-folder2 me-1"></i>${LG.utils.escapeHtml(binderName)}
                    </span>
                    <span class="${courtBadge}">${LG.utils.escapeHtml(c.court || 'Court')}</span>
                    <span class="badge bg-secondary">${c.year || '—'}</span>
                    ${c.outcome ? `<span class="badge badge-gold">${LG.utils.escapeHtml(c.outcome)}</span>` : ''}
                    <span class="badge bg-success bg-opacity-15 text-success border border-success border-opacity-30" style="font-size: 0.72rem;">
                      <i class="bi bi-shield-check me-1"></i>${LG.utils.escapeHtml(precedentialStatus)}
                    </span>
                    ${c.official_citation ? `<span class="badge bg-dark text-warning border border-secondary border-opacity-25 font-mono" style="font-size: 0.7rem;">${LG.utils.escapeHtml(c.official_citation)}</span>` : ''}
                    ${c.judge ? `<span class="small text-secondary"><i class="bi bi-person-fill me-1"></i>${LG.utils.escapeHtml(c.judge)}</span>` : ''}
                  </div>
                </div>

                <div class="d-flex align-items-center gap-2">
                  <button type="button" class="btn btn-sm btn-judicial-outline edit-bookmark-btn" 
                    data-id="${encodeURIComponent(b.id)}"
                    data-title="${LG.utils.escapeHtml(c.title || 'Case')}"
                    data-binder="${LG.utils.escapeHtml(binderName)}"
                    data-notes="${LG.utils.escapeHtml(b.notes || '')}"
                    title="Edit Research Note or Move Binder">
                    <i class="bi bi-pencil-square me-1"></i>Edit
                  </button>
                  <button type="button" class="btn btn-sm btn-judicial-outline text-danger delete-bookmark-btn" data-id="${encodeURIComponent(b.id)}" title="Remove Bookmark">
                    <i class="bi bi-trash3"></i>
                  </button>
                </div>
              </div>

              ${b.notes ? `
                <div class="p-2 px-3 rounded bg-dark border border-secondary border-opacity-25 small text-secondary my-2">
                  <div class="d-flex align-items-center justify-content-between">
                    <strong class="text-warning"><i class="bi bi-sticky-fill me-1"></i>Advocate Research Note:</strong>
                  </div>
                  <div class="mt-1 text-light">${LG.utils.escapeHtml(b.notes)}</div>
                </div>
              ` : `
                <div class="p-2 px-3 rounded bg-dark bg-opacity-40 border border-secondary border-opacity-10 small text-secondary my-2">
                  <em>No private notes attached. Click "Edit" to record research memo or specific propositions.</em>
                </div>
              `}

              ${c.ratio_decidendi ? `
                <div class="small text-secondary mb-2 fst-italic">
                  <strong class="text-light">Judicial Ratio:</strong> ${LG.utils.escapeHtml(c.ratio_decidendi.substring(0, 220))}...
                </div>
              ` : ''}

              <!-- Actions Bar -->
              <div class="d-flex align-items-center justify-content-between pt-2 border-top border-secondary border-opacity-15 flex-wrap gap-2">
                <div class="d-flex align-items-center gap-2">
                  <a href="case-viewer.html?id=${encodeURIComponent(c.id || b.case_id)}" class="btn btn-sm btn-gold">
                    <i class="bi bi-book-half me-1"></i>Read Judgment
                  </a>
                  <a href="case-compare.html?case1=${encodeURIComponent(c.id || b.case_id)}" class="btn btn-sm btn-judicial-outline">
                    <i class="bi bi-columns-gap me-1"></i>Compare
                  </a>
                  <button type="button" class="btn btn-sm btn-judicial-outline copy-cite-btn" data-citation="${LG.utils.escapeHtml(citation)}">
                    <i class="bi bi-quote me-1"></i>Copy Citation
                  </button>
                </div>

                <div class="small text-secondary">
                  Saved on ${LG.utils.formatDate(b.created_at)}
                </div>
              </div>
            </div>
          `;
        }).join('');

        $container.html(html).removeClass('d-none');

        // Copy Citation
        $('.copy-cite-btn').on('click', function () {
          const cite = $(this).data('citation');
          LG.utils.copyToClipboard(cite, 'Precedent citation copied!');
        });

        // Edit Bookmark Modal trigger
        $('.edit-bookmark-btn').on('click', function () {
          const bid = $(this).data('id');
          const title = $(this).data('title');
          const binder = $(this).data('binder');
          const notes = $(this).data('notes');

          $('#edit-bm-id').val(bid);
          $('#edit-bm-title').text(title);
          $('#edit-bm-binder-select').val(binder);
          $('#edit-bm-custom-binder').val('');
          $('#edit-bm-notes').val(notes);

          const modal = new bootstrap.Modal(document.getElementById('editBookmarkModal'));
          modal.show();
        });

        // Attach Delete Handler
        $('.delete-bookmark-btn').on('click', function () {
          const bid = $(this).data('id');
          if (!confirm('Are you sure you want to remove this case from your research binders?')) {
            return;
          }
          LG.api.bookmarks.remove(bid)
            .done(function () {
              LG.toast('Bookmark removed.', 'info');
              $(`#bookmark-card-${bid}`).fadeOut(300, function () {
                $(this).remove();
                if ($container.children().length === 0) {
                  $container.addClass('d-none');
                  $empty.removeClass('d-none');
                  $badgeCount.text('0 Cases Saved');
                }
              });
              loadBinders();
            })
            .fail(function () {
              LG.toast('Failed to remove bookmark.', 'danger');
            });
        });
      })
      .fail(function (xhr) {
        let msg = 'Failed to load bookmarks.';
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

  // Filter binder on select change
  $binderSelect.on('change', function () {
    currentBinder = $(this).val();
    loadBookmarks();
  });

  // Empty view switch to all
  $('#empty-all-binders-btn').on('click', function () {
    currentBinder = 'all';
    $binderSelect.val('all');
    loadBookmarks();
  });

  // Create New Binder
  $('#confirm-new-binder-btn').on('click', function () {
    const newName = $('#new-binder-name-input').val().trim();
    if (!newName) {
      LG.toast('Please enter a binder name.', 'warning');
      return;
    }
    bootstrap.Modal.getInstance(document.getElementById('newBinderModal')).hide();
    $('#new-binder-name-input').val('');
    
    currentBinder = newName;
    loadBinders().then(function () {
      $binderSelect.val(newName);
      loadBookmarks();
      LG.toast(`Switched to binder '${newName}'. Save cases from Case Viewer or Search to populate it!`, 'success');
    });
  });

  // Save Edit Bookmark
  $('#save-bookmark-edit-btn').on('click', function () {
    const bid = $('#edit-bm-id').val();
    const customBinder = $('#edit-bm-custom-binder').val().trim();
    const binderName = customBinder || $('#edit-bm-binder-select').val();
    const notes = $('#edit-bm-notes').val().trim();

    LG.api.bookmarks.update(bid, {
      binder_name: binderName,
      notes: notes
    })
    .done(function () {
      LG.toast('Bookmark and notes updated successfully.', 'success');
      bootstrap.Modal.getInstance(document.getElementById('editBookmarkModal')).hide();
      loadBinders().then(loadBookmarks);
    })
    .fail(function () {
      LG.toast('Failed to update bookmark.', 'danger');
    });
  });

  // Export Bibliography Handler
  $('#export-citations-btn').off('click').on('click', function () {
    if (!cachedBookmarks || cachedBookmarks.length === 0) {
      LG.toast('No bookmarks to export.', 'warning');
      return;
    }
    let bib = `# RESEARCH BIBLIOGRAPHY & CITATOR INDEX\n*Generated by LexGuard Judicial Platform · ${new Date().toLocaleDateString()}*\n\n`;
    cachedBookmarks.forEach(function (b, idx) {
      const c = b.case || {};
      bib += `${idx + 1}. **${c.title || 'Case'}**, (${c.year || ''}) ${c.court || ''}\n`;
      if (c.official_citation) bib += `   *Citation:* ${c.official_citation}\n`;
      if (c.case_no) bib += `   *Case No:* ${c.case_no}  |  *CNR:* ${c.cnr_number || c.cnr || 'N/A'}\n`;
      if (c.precedential_status) bib += `   *Precedential Authority:* ${c.precedential_status}\n`;
      if (b.binder_name) bib += `   *Binder:* ${b.binder_name}\n`;
      if (c.ratio_decidendi) bib += `   *Ratio:* ${c.ratio_decidendi.substring(0, 160)}...\n`;
      if (b.notes) bib += `   *Advocate Memo:* ${b.notes}\n`;
      bib += `\n`;
    });
    LG.utils.copyToClipboard(bib, 'Bibliography citations copied to clipboard!');
  });

  // Export Legal Research Memorandum Handler
  $('#export-memo-btn').on('click', function () {
    if (!cachedBookmarks || cachedBookmarks.length === 0) {
      LG.toast('No precedents in this binder to generate a memorandum.', 'warning');
      return;
    }

    $loading.removeClass('d-none');
    LG.api.bookmarks.exportMemo(currentBinder)
      .done(function (data) {
        $('#memo-binder-title').text(data.binder_name || 'All Saved Precedents');
        $('#memo-cases-count').text(`${data.total_cases} Authorities`);
        $('#memo-raw-markdown').val(data.markdown_memorandum);

        // Format HTML for rendered view
        let renderHtml = `
          <div class="text-center pb-3 mb-4 border-bottom border-warning border-opacity-40">
            <h2 class="text-warning fw-bold mb-1" style="font-family: 'Playfair Display', serif;">LEXGUARD ADVOCATE RESEARCH MEMORANDUM</h2>
            <div class="text-secondary small text-uppercase letter-spacing-1">Subject Matter Binder: <strong class="text-light">${LG.utils.escapeHtml(data.binder_name)}</strong></div>
            <div class="text-secondary small mt-1">Generated: ${new Date().toLocaleDateString('en-IN', { year: 'numeric', month: 'long', day: 'numeric' })} &bull; Total Authorities Cited: ${data.total_cases}</div>
          </div>
        `;

        (data.items || []).forEach(function (item) {
          renderHtml += `
            <div class="mb-4 p-3 rounded bg-dark border border-secondary border-opacity-30">
              <div class="d-flex justify-content-between align-items-start mb-2 flex-wrap gap-2">
                <h4 class="h5 text-warning mb-0" style="font-family: 'Playfair Display', serif;">
                  [${item.index}] ${LG.utils.escapeHtml(item.title)}
                </h4>
                <span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-30">
                  ${LG.utils.escapeHtml(item.precedential_status || 'Good Law')}
                </span>
              </div>
              <div class="small text-secondary mb-2">
                <strong>Court:</strong> ${LG.utils.escapeHtml(item.court)} (${item.year}) &bull; 
                <strong>Case No:</strong> ${LG.utils.escapeHtml(item.case_no)} &bull; 
                <strong>Citation:</strong> <code class="text-warning">${LG.utils.escapeHtml(item.official_citation || 'LexGuard Precedent')}</code>
              </div>
              ${item.judge ? `<div class="small text-secondary mb-2"><strong>Bench:</strong> ${LG.utils.escapeHtml(item.judge)}</div>` : ''}
              ${item.ratio_decidendi ? `
                <div class="small p-2 bg-black bg-opacity-40 rounded mb-2 text-light" style="border-left: 3px solid #d4af37;">
                  <strong>Judicial Ratio:</strong> ${LG.utils.escapeHtml(item.ratio_decidendi)}
                </div>
              ` : ''}
              ${item.notes ? `
                <div class="small p-2 bg-primary bg-opacity-10 border border-primary border-opacity-20 rounded text-light">
                  <strong class="text-warning"><i class="bi bi-pin-angle-fill me-1"></i>Advocate Argument / Note:</strong> ${LG.utils.escapeHtml(item.notes)}
                </div>
              ` : ''}
              <div class="small font-mono text-secondary mt-2" style="font-size: 0.68rem;">
                Cryptographic Seal: ${item.file_hash}
              </div>
            </div>
          `;
        });

        $('#memo-rendered-content').html(renderHtml);

        const modal = new bootstrap.Modal(document.getElementById('memoModal'));
        modal.show();
      })
      .fail(function () {
        LG.toast('Failed to generate research memorandum.', 'danger');
      })
      .always(function () {
        $loading.addClass('d-none');
      });
  });

  // Switch between Rendered and Markdown View
  $('#memo-view-rendered-btn').on('click', function () {
    $(this).addClass('active');
    $('#memo-view-markdown-btn').removeClass('active');
    $('#memo-rendered-content').removeClass('d-none');
    $('#memo-raw-markdown').addClass('d-none');
  });

  $('#memo-view-markdown-btn').on('click', function () {
    $(this).addClass('active');
    $('#memo-view-rendered-btn').removeClass('active');
    $('#memo-rendered-content').addClass('d-none');
    $('#memo-raw-markdown').removeClass('d-none');
  });

  // Copy Memorandum Markdown
  $('#memo-copy-btn').on('click', function () {
    const md = $('#memo-raw-markdown').val();
    LG.utils.copyToClipboard(md, 'Legal Memorandum copied to clipboard in markdown format!');
  });

  // Download .md Memorandum
  $('#memo-download-btn').on('click', function () {
    const md = $('#memo-raw-markdown').val();
    const binder = currentBinder === 'all' ? 'Legal_Research' : currentBinder.replace(/[^a-zA-Z0-9]/g, '_');
    const filename = `LexGuard_Memo_${binder}_${new Date().toISOString().slice(0, 10)}.md`;
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    LG.toast(`Downloaded ${filename}`, 'success');
  });

  // Print Memorandum
  $('#memo-print-btn').on('click', function () {
    const printContent = document.getElementById('memo-rendered-content').innerHTML;
    const printWindow = window.open('', '_blank', 'width=900,height=700');
    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>LexGuard Legal Research Memorandum</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.3/css/bootstrap.min.css">
        <style>
          body { font-family: 'Playfair Display', serif; padding: 40px; color: #111; background: #fff; line-height: 1.6; }
          .bg-dark, .bg-black { background: #fff !important; color: #222 !important; border: 1px solid #ddd !important; }
          .text-warning, .text-light { color: #111 !important; }
          .text-secondary { color: #555 !important; }
          .badge { border: 1px solid #333 !important; color: #111 !important; }
          @media print { body { padding: 0; } }
        </style>
      </head>
      <body>
        ${printContent}
      </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(function () {
      printWindow.print();
    }, 500);
  });

  // Initial Data Load
  loadBinders().then(loadBookmarks);
});
