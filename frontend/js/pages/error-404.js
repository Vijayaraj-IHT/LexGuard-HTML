    $(document).ready(function () {
      $('#req-path').text(window.location.pathname + window.location.search);
      $('#diag-time').text(new Date().toUTCString());

      $('#error-search-form').on('submit', function (e) {
        e.preventDefault();
        const q = $('#error-search-input').val().trim();
        if (q) {
          window.location.href = 'search.html?q=' + encodeURIComponent(q);
        }
      });
    });
