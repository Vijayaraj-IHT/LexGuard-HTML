"""
Updates case-viewer.html with Citizen vs Advocate mode toggle and citizen explainer card.
"""
with open('e:/SEM 5 PROJECT/Lexguard/lexguard-html/case-viewer.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Insert Mode Toggle into actions
toggle_html = """          <!-- Mode Toggle: Advocate vs Citizen -->
          <div class="btn-group btn-group-sm" role="group" aria-label="Viewer Mode Toggle">
            <input type="radio" class="btn-check" name="viewerMode" id="mode-advocate" autocomplete="off" checked>
            <label class="btn btn-judicial-outline" for="mode-advocate" title="Technical Legal Analysis"><i class="bi bi-briefcase me-1 text-warning"></i>Advocate View</label>

            <input type="radio" class="btn-check" name="viewerMode" id="mode-citizen" autocomplete="off">
            <label class="btn btn-judicial-outline" for="mode-citizen" title="Plain-English Explanation"><i class="bi bi-person me-1 text-info"></i>Citizen View</label>
          </div>
"""

old_action = '<button type="button" class="btn btn-sm btn-judicial-outline" id="action-case-brief-btn">'
if old_action in content and 'mode-citizen' not in content:
    content = content.replace(old_action, toggle_html + '          ' + old_action)

# 2. Insert Citizen Card before Ratio Decidendi
citizen_card_html = """              <!-- Citizen Plain-Language Card (Shown in Citizen View) -->
              <div class="card card-judicial p-4 mb-3 border-info border-opacity-30 d-none" id="citizen-card">
                <div class="d-flex align-items-center gap-2 mb-2">
                  <i class="bi bi-info-circle-fill fs-4 text-info"></i>
                  <h2 class="h5 fw-bold text-info mb-0">Plain-English Summary for Citizens</h2>
                  <span class="badge bg-info bg-opacity-10 text-info ms-auto">Simplified Law</span>
                </div>
                <p class="text-light fs-6 lh-base mb-3" id="citizen-summary-text">
                  Loading plain-English summary...
                </p>
                <div class="bg-dark p-3 rounded border border-secondary border-opacity-25">
                  <div class="small fw-semibold text-secondary mb-1">Practical Takeaway:</div>
                  <div class="small text-light" id="citizen-takeaway"></div>
                </div>
              </div>

"""

ratio_marker = '<!-- Ratio Decidendi -->'
if ratio_marker in content and 'citizen-card' not in content:
    content = content.replace(ratio_marker, citizen_card_html + '              ' + ratio_marker)

with open('e:/SEM 5 PROJECT/Lexguard/lexguard-html/case-viewer.html', 'w', encoding='utf-8') as f:
    f.write(content)
with open('e:/SEM 5 PROJECT/LexGuard-HTML/frontend/case-viewer.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated case-viewer.html in both repositories successfully!')
