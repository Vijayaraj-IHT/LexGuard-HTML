"""
update_advocate_binders_ui.py
Implements Phase 4 Advocate Research Binders UI:
- Dynamic Binder categorization and filtering
- Modal to create custom binders
- Modal to edit notes and move cases between binders
- Legal Research Memorandum generation with formatted view and export/print
- Synced across Lexguard (lexguard-html) and LexGuard-HTML (frontend)
"""
import os

BOOKMARKS_HTML = """<!DOCTYPE html>
<html lang="en" data-theme="light" data-bs-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <link rel="alternate icon" href="favicon.ico">
  <title>Advocate Research Binders &amp; Bookmarks · LexGuard</title>

  <!-- Google Fonts & CDN CSS -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:ital,wght@0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.3/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap-icons/1.11.3/font/bootstrap-icons.min.css">

  <!-- LexGuard Styles -->
  <link rel="stylesheet" href="css/lexguard.css">
  <link rel="stylesheet" href="css/components.css">
</head>
<body data-active-page="bookmarks">

  <!-- Shared Top Navbar & Left Sidebar slots -->
  <div id="navbar-slot"></div>
  <div id="sidebar-slot"></div>

  <!-- Main Content -->
  <main class="lg-main">
    <div class="container-fluid px-0" style="max-width: 1040px;">

      <!-- Page Header -->
      <div class="lg-page-header mb-3">
        <div>
          <h1 class="lg-page-title">
            <i class="bi bi-folder2-open text-warning"></i>
            <span>Advocate Research Binders</span>
          </h1>
          <p class="lg-page-subtitle">
            Organized judicial precedent binders, private case notes, and exportable research memorandums for active court matters.
          </p>
        </div>
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <span class="badge bg-secondary" id="bookmarks-count-badge">0 Cases Saved</span>
          <button type="button" class="btn btn-sm btn-gold" id="export-memo-btn">
            <i class="bi bi-file-earmark-medical me-1"></i>Export Legal Memo
          </button>
          <button type="button" class="btn btn-sm btn-judicial-outline" id="export-citations-btn">
            <i class="bi bi-file-earmark-arrow-down me-1 text-warning"></i>Bibliography
          </button>
        </div>
      </div>

      <!-- Binder Filter & Control Bar -->
      <div class="card card-judicial p-3 mb-4 shadow-sm">
        <div class="row g-3 align-items-center">
          <div class="col-md-6 d-flex align-items-center gap-2">
            <label for="binder-select" class="form-label text-secondary small mb-0 text-nowrap fw-semibold">
              <i class="bi bi-folder-fill text-warning me-1"></i>Active Binder:
            </label>
            <select class="form-select form-select-sm bg-dark text-light border-secondary" id="binder-select">
              <option value="all">All Binders (All Saved Precedents)</option>
              <option value="General Research">General Research</option>
            </select>
          </div>
          <div class="col-md-6 d-flex justify-content-md-end align-items-center gap-2 flex-wrap">
            <button type="button" class="btn btn-sm btn-judicial-outline" id="new-binder-btn" data-bs-toggle="modal" data-bs-target="#newBinderModal">
              <i class="bi bi-folder-plus text-warning me-1"></i>Create New Binder
            </button>
            <span class="text-secondary small d-none d-md-inline" id="binder-status-label">Viewing all saved authorities</span>
          </div>
        </div>
      </div>

      <!-- Loading Spinner -->
      <div id="bookmarks-loading" class="text-center py-5">
        <div class="spinner-border text-warning" role="status"></div>
        <p class="text-secondary small mt-2">Loading your saved research binders...</p>
      </div>

      <!-- Bookmarks List Container -->
      <div id="bookmarks-container" class="d-none"></div>

      <!-- Empty State -->
      <div id="bookmarks-empty" class="card card-judicial text-center p-5 d-none">
        <i class="bi bi-folder-x text-secondary display-6 mb-3"></i>
        <h2 class="h5 text-light">No Precedents in this Binder</h2>
        <p class="text-secondary small mb-4" style="max-width: 460px; margin: 0 auto;">
          You haven't saved any judicial authorities to this binder yet. Browse the repository or search rulings to curate citations for your legal matters.
        </p>
        <div class="d-flex justify-content-center gap-2">
          <a href="search.html" class="btn btn-gold">
            <i class="bi bi-search me-1"></i>Search Precedents
          </a>
          <button type="button" class="btn btn-judicial-outline" id="empty-all-binders-btn">
            <i class="bi bi-folder2 me-1"></i>View All Binders
          </button>
        </div>
      </div>

    </div>
  </main>

  <!-- Modal: Create New Binder -->
  <div class="modal fade" id="newBinderModal" tabindex="-1" aria-labelledby="newBinderModalLabel" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
      <div class="modal-content bg-dark text-light border-secondary">
        <div class="modal-header border-secondary border-opacity-25">
          <h5 class="modal-title text-warning" id="newBinderModalLabel">
            <i class="bi bi-folder-plus me-2"></i>Create Advocate Research Binder
          </h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <div class="modal-body">
          <label for="new-binder-name-input" class="form-label text-secondary small fw-semibold">
            Binder / Subject Matter Name
          </label>
          <input type="text" class="form-control bg-dark text-light border-secondary" id="new-binder-name-input" placeholder="e.g., Section 482 Quashing / Anticipatory Bail" maxlength="80">
          <div class="form-text text-secondary small mt-2">
            Binders help categorize precedents by client petition, statutory provision, or legal topic.
          </div>
        </div>
        <div class="modal-footer border-secondary border-opacity-25">
          <button type="button" class="btn btn-sm btn-judicial-outline" data-bs-dismiss="modal">Cancel</button>
          <button type="button" class="btn btn-sm btn-gold" id="confirm-new-binder-btn">Create &amp; Switch Binder</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Modal: Edit Bookmark & Move Binder -->
  <div class="modal fade" id="editBookmarkModal" tabindex="-1" aria-labelledby="editBookmarkModalLabel" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered modal-lg">
      <div class="modal-content bg-dark text-light border-secondary">
        <div class="modal-header border-secondary border-opacity-25">
          <h5 class="modal-title text-warning" id="editBookmarkModalLabel">
            <i class="bi bi-pencil-square me-2"></i>Edit Research Note &amp; Binder
          </h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <div class="modal-body">
          <input type="hidden" id="edit-bm-id">
          <div class="mb-3">
            <label class="text-secondary small fw-semibold mb-1">Case Title</label>
            <div class="p-2 bg-secondary bg-opacity-10 rounded border border-secondary border-opacity-25 text-light fw-bold" id="edit-bm-title">
              Case Title Here
            </div>
          </div>
          <div class="mb-3">
            <label for="edit-bm-binder-select" class="form-label text-secondary small fw-semibold">
              Assign to Research Binder
            </label>
            <div class="row g-2">
              <div class="col-md-6">
                <select class="form-select bg-dark text-light border-secondary" id="edit-bm-binder-select">
                  <option value="General Research">General Research</option>
                </select>
              </div>
              <div class="col-md-6">
                <input type="text" class="form-control bg-dark text-light border-secondary" id="edit-bm-custom-binder" placeholder="Or type new binder name...">
              </div>
            </div>
          </div>
          <div class="mb-3">
            <label for="edit-bm-notes" class="form-label text-secondary small fw-semibold">
              Advocate Private Research Notes / Arguments
            </label>
            <textarea class="form-control bg-dark text-light border-secondary font-sans" id="edit-bm-notes" rows="4" placeholder="Record specific proposition, paragraph citations, or application to current brief..."></textarea>
          </div>
        </div>
        <div class="modal-footer border-secondary border-opacity-25">
          <button type="button" class="btn btn-sm btn-judicial-outline" data-bs-dismiss="modal">Cancel</button>
          <button type="button" class="btn btn-sm btn-gold" id="save-bookmark-edit-btn">Save Changes</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Modal: Research Memorandum Preview & Export -->
  <div class="modal fade" id="memoModal" tabindex="-1" aria-labelledby="memoModalLabel" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered modal-xl modal-dialog-scrollable">
      <div class="modal-content bg-dark text-light border-secondary">
        <div class="modal-header border-secondary border-opacity-25">
          <h5 class="modal-title text-warning" id="memoModalLabel">
            <i class="bi bi-file-earmark-medical me-2"></i>Advocate Legal Research Memorandum
          </h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <div class="modal-body p-4" id="memo-modal-body">
          <div class="d-flex justify-content-between align-items-center mb-3 pb-2 border-bottom border-secondary border-opacity-25 flex-wrap gap-2">
            <div class="text-secondary small">
              <strong class="text-warning" id="memo-binder-title">General Research</strong> &mdash; 
              <span id="memo-cases-count">0 Authorities</span>
            </div>
            <div class="btn-group btn-group-sm">
              <button type="button" class="btn btn-judicial-outline active" id="memo-view-rendered-btn">
                <i class="bi bi-eye me-1"></i>Formatted View
              </button>
              <button type="button" class="btn btn-judicial-outline" id="memo-view-markdown-btn">
                <i class="bi bi-markdown me-1"></i>Markdown Source
              </button>
            </div>
          </div>
          <!-- Rendered View -->
          <div id="memo-rendered-content" class="p-4 bg-black bg-opacity-30 rounded border border-secondary border-opacity-20 text-light" style="font-family: 'Playfair Display', serif; line-height: 1.8;"></div>
          <!-- Raw Markdown View -->
          <textarea id="memo-raw-markdown" class="form-control bg-black text-light font-mono small d-none" rows="16" readonly></textarea>
        </div>
        <div class="modal-footer border-secondary border-opacity-25">
          <button type="button" class="btn btn-sm btn-judicial-outline" id="memo-copy-btn">
            <i class="bi bi-clipboard me-1"></i>Copy Markdown
          </button>
          <button type="button" class="btn btn-sm btn-judicial-outline" id="memo-download-btn">
            <i class="bi bi-file-earmark-arrow-down me-1"></i>Download .md
          </button>
          <button type="button" class="btn btn-sm btn-gold" id="memo-print-btn">
            <i class="bi bi-printer me-1"></i>Print Memo
          </button>
          <button type="button" class="btn btn-sm btn-judicial-outline" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>

  <!-- CDN JS Dependencies -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.7.1/jquery.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.3/js/bootstrap.bundle.min.js"></script>

  <!-- LexGuard Core & Page Scripts -->
  <script src="js/lexguard-core.js"></script>
  <script src="js/lexguard-auth.js"></script>
  <script src="js/lexguard-toast.js"></script>
  <script src="js/lexguard-api.js"></script>
  <script src="js/lexguard-nav.js"></script>
  <script src="js/pages/bookmarks.js"></script>
</body>
</html>
"""

BOOKMARKS_JS = """/**
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
          const precedentialStatus = c.precedential_status || 'Precedential status not checked';

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
    let bib = `# RESEARCH BIBLIOGRAPHY & CITATOR INDEX\\n*Generated by LexGuard Judicial Platform · ${new Date().toLocaleDateString()}*\\n\\n`;
    cachedBookmarks.forEach(function (b, idx) {
      const c = b.case || {};
      bib += `${idx + 1}. **${c.title || 'Case'}**, (${c.year || ''}) ${c.court || ''}\\n`;
      if (c.official_citation) bib += `   *Citation:* ${c.official_citation}\\n`;
      if (c.case_no) bib += `   *Case No:* ${c.case_no}  |  *CNR:* ${c.cnr || 'N/A'}\\n`;
      if (c.precedential_status) bib += `   *Precedential Authority:* ${c.precedential_status}\\n`;
      if (b.binder_name) bib += `   *Binder:* ${b.binder_name}\\n`;
      if (c.ratio_decidendi) bib += `   *Ratio:* ${c.ratio_decidendi.substring(0, 160)}...\\n`;
      if (b.notes) bib += `   *Advocate Memo:* ${b.notes}\\n`;
      bib += `\\n`;
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
                  ${LG.utils.escapeHtml(item.precedential_status || 'Precedential status not checked')}
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
"""

def main():
    repos = [
        (r"e:\SEM 5 PROJECT\Lexguard\lexguard-html\bookmarks.html", r"e:\SEM 5 PROJECT\Lexguard\lexguard-html\js\pages\bookmarks.js"),
        (r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend\bookmarks.html", r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend\js\pages\bookmarks.js")
    ]
    for html_path, js_path in repos:
        if os.path.exists(os.path.dirname(html_path)):
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(BOOKMARKS_HTML)
            print("Wrote:", html_path)
        if os.path.exists(os.path.dirname(js_path)):
            with open(js_path, "w", encoding="utf-8") as f:
                f.write(BOOKMARKS_JS)
            print("Wrote:", js_path)

if __name__ == "__main__":
    main()
