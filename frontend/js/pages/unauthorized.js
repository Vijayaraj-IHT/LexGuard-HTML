    $(document).ready(function () {
      const user = LG.session.user();
      if (user) {
        $('#current-role-badge').html(LG.utils.getRoleBadge(user.role));
      } else {
        $('#current-role-badge').html('<span class="badge bg-secondary">Unauthenticated</span>');
      }

      $('#switch-account-btn').on('click', function () {
        LG.session.clear();
        window.location.href = 'login.html';
      });
    });
