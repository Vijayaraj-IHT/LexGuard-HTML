    $(document).ready(function () {
      // Dynamic live metrics from repository stats
      const apiBase = LG.config.API_BASE;
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
