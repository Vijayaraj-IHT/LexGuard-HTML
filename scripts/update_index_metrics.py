import os
import re

files_to_update = [
    r"e:\SEM 5 PROJECT\Lexguard\lexguard-html\index.html",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\index.html",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend\index.html",
]

NEW_CARDS = """      <!-- Trust Metrics & Infrastructure Row -->
      <div class="row g-3 mt-4 pt-2">
        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-dark font-serif mb-1" id="stat-courts-count">15 Courts</div>
            <div class="small text-secondary">Supreme Court &amp; High Courts</div>
          </div>
        </div>
        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-danger font-serif mb-1" id="stat-cases-count">130 Verified</div>
            <div class="small text-secondary">Precedents in Certified Repository</div>
          </div>
        </div>
        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-success font-serif mb-1" id="stat-audit-count">1,150+ Entries</div>
            <div class="small text-secondary">Tamper-Evident Audit Ledger</div>
          </div>
        </div>
        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-dark font-serif mb-1" id="stat-verified-count">100% Sealed</div>
            <div class="small text-secondary">Cryptographic Hash Registered</div>
          </div>
        </div>
      </div>"""

NEW_SCRIPT = """  <script>
    $(document).ready(function () {
      // Dynamic live metrics from repository stats
      const apiBase = (window.LexGuard && window.LexGuard.API_BASE_URL) || window.API_BASE_URL || 'http://127.0.0.1:8000/api/v1';
      $.ajax({
        url: apiBase + '/cases/stats',
        type: 'GET',
        xhrFields: { withCredentials: true },
        success: function (data) {
          if (data) {
            if (data.courts_covered) {
              $('#stat-courts-count').text(data.courts_covered + ' Courts');
            }
            if (data.total_cases) {
              $('#stat-cases-count').text(data.total_cases + ' Verified');
            }
            if (data.total_audit_entries) {
              $('#stat-audit-count').text(Number(data.total_audit_entries).toLocaleString() + ' Entries');
            }
            if (data.verified_cases) {
              $('#stat-verified-count').text(data.verified_cases + ' Sealed');
            }
          }
        },
        error: function () {
          // Graceful fallback
        }
      });

      $('#hero-search-form').on('submit', function (e) {
        e.preventDefault();
        const q = $('#hero-search-input').val().trim();
        if (q) {
          window.location.href = 'search.html?q=' + encodeURIComponent(q);
        } else {
          window.location.href = 'search.html';
        }
      });
    });
  </script>"""

for p in files_to_update:
    if not os.path.exists(p):
        print(f"Skipping {p}: file not found")
        continue

    with open(p, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace cards row
    cards_regex = re.compile(r'<!-- Trust Metrics & Infrastructure Row -->.*?</div>\s*</div>\s*</div>\s*</div>\s*</div>', re.DOTALL)
    if cards_regex.search(content):
        content = cards_regex.sub(NEW_CARDS, content)
        print(f"Updated cards in {p}")
    else:
        print(f"Cards regex did not match in {p}")

    # Replace script
    script_regex = re.compile(r'<script>\s*\$\(document\)\.ready\(function\s*\(\)\s*\{.*?hero-search-input.*?\}\);\s*</script>', re.DOTALL)
    if script_regex.search(content):
        content = script_regex.sub(NEW_SCRIPT, content)
        print(f"Updated script in {p}")
    else:
        print(f"Script regex did not match in {p}")

    with open(p, "w", encoding="utf-8") as f:
        f.write(content)

print("Done updating index.html files.")
