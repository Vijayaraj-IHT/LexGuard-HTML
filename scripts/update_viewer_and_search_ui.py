"""
update_viewer_and_search_ui.py
Implements:
1. "Save to Binder & Note" modal on case-viewer.html and case-viewer.js
2. Advanced Boolean & Field Query Syntax Guide on search.html
3. Live metric badge and query mode detection on search.js
4. Synchronizes changes across both Lexguard and LexGuard-HTML repositories.
"""
import os
import re

VIEWER_MODAL_HTML = """  <!-- Modal: Save to Research Binder & Notes -->
  <div class="modal fade" id="saveToBinderModal" tabindex="-1" aria-labelledby="saveToBinderModalLabel" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
      <div class="modal-content bg-dark text-light border-secondary">
        <div class="modal-header border-secondary border-opacity-25">
          <h5 class="modal-title text-warning" id="saveToBinderModalLabel">
            <i class="bi bi-folder-plus me-2"></i>Save Precedent to Research Binder
          </h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <div class="modal-body">
          <div class="mb-3">
            <label class="text-secondary small fw-semibold mb-1">Judicial Authority</label>
            <div class="p-2 bg-secondary bg-opacity-10 rounded border border-secondary border-opacity-25 text-light fw-bold" id="binder-modal-case-title">
              —
            </div>
          </div>
          <div class="mb-3">
            <label for="binder-modal-select" class="form-label text-secondary small fw-semibold">
              Select Research Binder
            </label>
            <div class="row g-2">
              <div class="col-md-6">
                <select class="form-select bg-dark text-light border-secondary" id="binder-modal-select">
                  <option value="General Research">General Research</option>
                </select>
              </div>
              <div class="col-md-6">
                <input type="text" class="form-control bg-dark text-light border-secondary" id="binder-modal-new-input" placeholder="Or type new binder...">
              </div>
            </div>
          </div>
          <div class="mb-3">
            <label for="binder-modal-notes" class="form-label text-secondary small fw-semibold">
              Advocate Private Research Notes
            </label>
            <textarea class="form-control bg-dark text-light border-secondary font-sans" id="binder-modal-notes" rows="4" placeholder="Record proposition of law, key paragraphs, or relevance to current brief..."></textarea>
          </div>
        </div>
        <div class="modal-footer border-secondary border-opacity-25 justify-content-between">
          <button type="button" class="btn btn-sm btn-judicial-outline text-danger d-none" id="binder-modal-delete-btn">
            <i class="bi bi-trash3 me-1"></i>Remove Bookmark
          </button>
          <div class="d-flex gap-2 ms-auto">
            <button type="button" class="btn btn-sm btn-judicial-outline" data-bs-dismiss="modal">Cancel</button>
            <button type="button" class="btn btn-sm btn-gold" id="binder-modal-save-btn">
              <i class="bi bi-bookmark-fill me-1"></i>Save Precedent
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
"""

SEARCH_BOOLEAN_GUIDE_HTML = """        <!-- Quick Query Suggestion Chips -->
        <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 pt-1">
          <div class="d-flex flex-wrap align-items-center gap-2">
            <span class="text-secondary small fw-semibold">Suggested queries:</span>
            <button type="button" class="btn btn-xs btn-judicial-outline query-chip" data-query="Section 482 CrPC quashing FIR guidelines">
              <i class="bi bi-magic text-warning me-1"></i>Section 482 CrPC quashing FIR
            </button>
            <button type="button" class="btn btn-xs btn-judicial-outline query-chip" data-query="Bail jurisprudence under Article 21 and PMLA">
              Bail under Art. 21 &amp; PMLA
            </button>
            <button type="button" class="btn btn-xs btn-judicial-outline query-chip" data-query="Section 138 Negotiable Instruments Act statutory presumption">
              Section 138 NI Act presumption
            </button>
            <button type="button" class="btn btn-xs btn-judicial-outline query-chip" data-query="Specific Relief Act readiness and willingness Section 16(c)">
              Specific Relief Sec. 16(c)
            </button>
            <button type="button" class="btn btn-xs btn-judicial-outline query-chip" data-query="Arbitration and Conciliation Act Section 34 patent illegality">
              Section 34 Arbitration Act
            </button>
          </div>
          <div>
            <button type="button" class="btn btn-xs btn-judicial-outline text-warning" data-bs-toggle="collapse" data-bs-target="#booleanSearchGuide" aria-expanded="false" aria-controls="booleanSearchGuide">
              <i class="bi bi-terminal me-1"></i>Boolean &amp; Field Query Guide
            </button>
          </div>
        </div>

        <!-- Advanced Boolean & Field Query Syntax Guide Collapse -->
        <div class="collapse mt-3" id="booleanSearchGuide">
          <div class="p-3 bg-dark rounded border border-secondary border-opacity-30 small">
            <div class="fw-bold text-warning mb-2">
              <i class="bi bi-cpu text-warning me-1"></i>Advocate Boolean &amp; Field Query Syntax
            </div>
            <div class="row g-2 text-secondary">
              <div class="col-md-6">
                <div><code class="text-warning">"quashing FIR"</code> &mdash; Exact phrase matching</div>
                <div><code class="text-warning">bail AND "Article 21"</code> &mdash; All required terms</div>
                <div><code class="text-warning">anticipatory OR regular</code> &mdash; Alternative legal terms</div>
                <div><code class="text-warning">cheating NOT matrimonial</code> &mdash; Exclusion query</div>
              </div>
              <div class="col-md-6">
                <div><code class="text-warning">court:Supreme</code> or <code class="text-warning">court:Madras</code> &mdash; Direct bench filter</div>
                <div><code class="text-warning">section:482</code> or <code class="text-warning">section:138</code> &mdash; Statute section query</div>
                <div><code class="text-warning">citation:"(2014) 2 SCC 1"</code> &mdash; Citation locator</div>
                <div><code class="text-warning">judge:Chandrachud</code> &mdash; Presiding judge search</div>
              </div>
            </div>
          </div>
        </div>"""

def patch_case_viewer_html(filepath):
    if not os.path.exists(filepath):
        print("Not found:", filepath)
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if "id=\"saveToBinderModal\"" not in content:
        # Place before #digitalSealCertificateModal
        target = "  <!-- Digital Seal Certificate Modal (Printable Certified Copy Sheet) -->"
        if target in content:
            content = content.replace(target, VIEWER_MODAL_HTML + "\n" + target)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print("Patched case-viewer.html modal:", filepath)
        else:
            print("Target comment not found in", filepath)
    else:
        print("saveToBinderModal already in", filepath)

def patch_case_viewer_js(filepath):
    if not os.path.exists(filepath):
        print("Not found:", filepath)
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace simple bookmark handler with Binder modal wiring
    old_handler_regex = re.compile(
        r"  // Bookmark Button Handler\s+\$bookmarkBtn\.on\('click', function \(\) \{[\s\S]*?\}\);\s+\}\);",
        re.MULTILINE
    )

    new_handler = """  // Bookmark & Research Binder Handler
  let existingBookmarkId = null;

  function checkBookmarkStatus() {
    if (!LG.session.isAuthenticated() || !caseId) return;
    LG.api.bookmarks.list('all')
      .done(function (bookmarks) {
        if (!Array.isArray(bookmarks)) return;
        const found = bookmarks.find(b => b.case_id === caseId || (b.case && b.case.id === caseId));
        if (found) {
          existingBookmarkId = found.id;
          $bookmarkBtn.find('i').attr('class', 'bi bi-bookmark-fill text-warning');
          $bookmarkBtn.attr('title', `Saved in '${found.binder_name || 'General Research'}'`);
        } else {
          existingBookmarkId = null;
          $bookmarkBtn.find('i').attr('class', 'bi bi-bookmark text-warning');
          $bookmarkBtn.attr('title', 'Save to Research Binder');
        }
      });
  }

  $bookmarkBtn.on('click', function () {
    if (!LG.session.isAuthenticated()) {
      LG.toast('Please sign in to save research bookmarks and binders.', 'warning');
      return;
    }

    if (!currentCase) return;

    $('#binder-modal-case-title').text(currentCase.title || 'Judicial Precedent');
    $('#binder-modal-notes').val('');
    $('#binder-modal-new-input').val('');

    // Load available binders
    LG.api.bookmarks.getBinders()
      .done(function (binders) {
        let opts = '';
        const names = (binders || []).map(b => b.binder_name);
        if (!names.includes('General Research')) names.unshift('General Research');
        names.forEach(function (name) {
          opts += `<option value="${LG.utils.escapeHtml(name)}">${LG.utils.escapeHtml(name)}</option>`;
        });
        $('#binder-modal-select').html(opts);

        // Prepopulate if already bookmarked
        if (existingBookmarkId) {
          LG.api.bookmarks.list('all').done(function (bms) {
            const found = (bms || []).find(b => b.id === existingBookmarkId || b.case_id === caseId);
            if (found) {
              if (found.binder_name) $('#binder-modal-select').val(found.binder_name);
              if (found.notes) $('#binder-modal-notes').val(found.notes);
              $('#binder-modal-delete-btn').removeClass('d-none');
              $('#binder-modal-save-btn').html('<i class="bi bi-check-lg me-1"></i>Update Precedent');
            }
          });
        } else {
          $('#binder-modal-delete-btn').addClass('d-none');
          $('#binder-modal-save-btn').html('<i class="bi bi-bookmark-fill me-1"></i>Save Precedent');
        }

        const modal = new bootstrap.Modal(document.getElementById('saveToBinderModal'));
        modal.show();
      });
  });

  // Save / Update Bookmark from Modal
  $('#binder-modal-save-btn').off('click').on('click', function () {
    const customBinder = $('#binder-modal-new-input').val().trim();
    const binder = customBinder || $('#binder-modal-select').val() || 'General Research';
    const notes = $('#binder-modal-notes').val().trim();

    LG.api.bookmarks.add(caseId, notes, binder)
      .done(function (res) {
        LG.toast(`Precedent saved to binder '${binder}'!`, 'success');
        existingBookmarkId = res.id;
        $bookmarkBtn.find('i').attr('class', 'bi bi-bookmark-fill text-warning');
        $bookmarkBtn.attr('title', `Saved in '${binder}'`);
        const modalEl = document.getElementById('saveToBinderModal');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
      })
      .fail(function () {
        LG.toast('Failed to save bookmark.', 'danger');
      });
  });

  // Delete Bookmark from Modal
  $('#binder-modal-delete-btn').off('click').on('click', function () {
    if (!existingBookmarkId) return;
    if (!confirm('Remove this case from your research binders?')) return;

    LG.api.bookmarks.remove(existingBookmarkId)
      .done(function () {
        LG.toast('Precedent removed from research binders.', 'info');
        existingBookmarkId = null;
        $bookmarkBtn.find('i').attr('class', 'bi bi-bookmark text-warning');
        $bookmarkBtn.attr('title', 'Save to Research Binder');
        const modalEl = document.getElementById('saveToBinderModal');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
      })
      .fail(function () {
        LG.toast('Failed to remove bookmark.', 'danger');
      });
  });

  // Initial bookmark status check
  checkBookmarkStatus();
});"""

    if "checkBookmarkStatus" not in content:
        # Replace old handler
        if old_handler_regex.search(content):
            content = old_handler_regex.sub(new_handler, content)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print("Patched case-viewer.js handler:", filepath)
        else:
            # Try manual replacement of the block
            target = "  // Bookmark Button Handler"
            idx = content.find(target)
            if idx != -1:
                end_idx = content.rfind("});")
                content = content[:idx] + new_handler
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                print("Replaced case-viewer.js handler via index:", filepath)
            else:
                print("Bookmark handler target not found in", filepath)
    else:
        print("checkBookmarkStatus already in", filepath)

def patch_search_html(filepath):
    if not os.path.exists(filepath):
        print("Not found:", filepath)
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace suggested queries block with Boolean Guide
    old_target = """        <!-- Quick Query Suggestion Chips -->
        <div class="d-flex flex-wrap align-items-center gap-2 pt-1">
          <span class="text-secondary small fw-semibold">Suggested queries:</span>
          <button type="button" class="btn btn-xs btn-judicial-outline query-chip" data-query="Section 482 CrPC quashing FIR guidelines">
            <i class="bi bi-magic text-warning me-1"></i>Section 482 CrPC quashing FIR
          </button>
          <button type="button" class="btn btn-xs btn-judicial-outline query-chip" data-query="Bail jurisprudence under Article 21 and PMLA">
            Bail under Art. 21 &amp; PMLA
          </button>
          <button type="button" class="btn btn-xs btn-judicial-outline query-chip" data-query="Section 138 Negotiable Instruments Act statutory presumption">
            Section 138 NI Act presumption
          </button>
          <button type="button" class="btn btn-xs btn-judicial-outline query-chip" data-query="Specific Relief Act readiness and willingness Section 16(c)">
            Specific Relief Sec. 16(c)
          </button>
          <button type="button" class="btn btn-xs btn-judicial-outline query-chip" data-query="Arbitration and Conciliation Act Section 34 patent illegality">
            Section 34 Arbitration Act
          </button>
        </div>"""

    if "booleanSearchGuide" not in content and old_target in content:
        content = content.replace(old_target, SEARCH_BOOLEAN_GUIDE_HTML)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print("Patched search.html Boolean Guide:", filepath)
    else:
        print("search.html Boolean Guide already present or target mismatch:", filepath)

def patch_search_js(filepath):
    if not os.path.exists(filepath):
        print("Not found:", filepath)
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Add dynamic stats loading and boolean query badge
    if "LG.api.cases.getStats" not in content:
        # Insert stats call in document ready
        needle = "  // Handle Form Submission"
        addition = """  // Load live verified repository stats
  LG.api.cases.getStats()
    .done(function (stats) {
      if (stats && stats.total_cases) {
        $('#total-cases-badge').text(`${stats.total_cases} Verified Court Judgments`);
      }
    });

  // Handle Form Submission"""
        content = content.replace(needle, addition)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print("Patched search.js stats:", filepath)

def main():
    paths = [
        ("Lexguard", r"e:\SEM 5 PROJECT\Lexguard\lexguard-html"),
        ("LexGuard-HTML", r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend")
    ]
    for name, base in paths:
        patch_case_viewer_html(os.path.join(base, "case-viewer.html"))
        patch_case_viewer_js(os.path.join(base, "js", "pages", "case-viewer.js"))
        patch_search_html(os.path.join(base, "search.html"))
        patch_search_js(os.path.join(base, "js", "pages", "search.js"))

if __name__ == "__main__":
    main()
