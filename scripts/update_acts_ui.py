"""
Updates acts-explorer.html with the codified section detail modal.
"""
with open('e:/SEM 5 PROJECT/Lexguard/lexguard-html/acts-explorer.html', 'r', encoding='utf-8') as f:
    content = f.read()

modal_html = """
  <!-- Codified Statute Section Detail & Case Matching Modal -->
  <div class="modal fade" id="statute-detail-modal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-lg modal-dialog-scrollable">
      <div class="modal-content card-judicial border border-secondary border-opacity-25 shadow-lg">
        <div class="modal-header border-bottom border-secondary border-opacity-25">
          <div>
            <span class="badge bg-danger mb-1" id="modal-act-code">ACT</span>
            <h5 class="modal-title font-serif fw-bold text-light" id="modal-section-title">Section Details</h5>
            <div class="small text-secondary" id="modal-act-title">Statute Name</div>
          </div>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <div class="modal-body p-4">
          <!-- Codified Bare Act Text Box -->
          <div class="card p-3 mb-3 bg-dark border-secondary border-opacity-25">
            <div class="small fw-bold text-warning mb-2">
              <i class="bi bi-file-earmark-code me-1"></i>Official Legislative Codified Text (Bare Act)
            </div>
            <div class="text-light small font-serif lh-base" id="modal-bare-text" style="white-space: pre-wrap;">
              Loading bare act text...
            </div>
          </div>

          <!-- Judicial Commentary Box -->
          <div class="card p-3 mb-4 bg-dark border-secondary border-opacity-25">
            <div class="small fw-bold text-info mb-1">
              <i class="bi bi-lightbulb me-1"></i>Judicial Commentary &amp; Scope
            </div>
            <div class="text-secondary small lh-base" id="modal-explanation">
              Loading commentary...
            </div>
          </div>

          <!-- Matching Precedent Cases in LexGuard -->
          <div>
            <div class="d-flex align-items-center justify-content-between mb-2">
              <h6 class="fw-bold text-light mb-0">
                <i class="bi bi-journal-bookmark me-1 text-danger"></i>Interpreting Judgments in LexGuard (<span id="modal-cases-count">0</span>)
              </h6>
              <a href="#" id="modal-search-all-link" class="small text-warning text-decoration-none" target="_blank">
                Search all in Precedent Engine &rarr;
              </a>
            </div>
            <div class="d-flex flex-column gap-2" id="modal-cases-list">
              <!-- Dynamically populated case cards -->
            </div>
          </div>
        </div>
        <div class="modal-footer border-top border-secondary border-opacity-25">
          <button type="button" class="btn btn-sm btn-judicial-outline" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>
"""

target = '</main>'
if target in content and 'statute-detail-modal' not in content:
    content = content.replace(target, target + '\n' + modal_html)
    with open('e:/SEM 5 PROJECT/Lexguard/lexguard-html/acts-explorer.html', 'w', encoding='utf-8') as f:
        f.write(content)
    with open('e:/SEM 5 PROJECT/LexGuard-HTML/frontend/acts-explorer.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Modal added to acts-explorer.html and LexGuard-HTML/frontend successfully!')
else:
    print('Already present or target not found.')
