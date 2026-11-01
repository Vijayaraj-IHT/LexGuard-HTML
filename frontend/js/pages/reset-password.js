    $(document).ready(function () {
      const urlParams = new URLSearchParams(window.location.search);
      const token = urlParams.get('token');
      const email = urlParams.get('email');

      if (!token || !email) {
        $('#reset-alert').removeClass('d-none').addClass('alert-danger').html(`
          <i class="bi bi-exclamation-triangle-fill me-1"></i>Invalid or missing recovery token. Please request a new link from the <a href="forgot-password.html" class="alert-link">recovery portal</a>.
        `);
        $('#reset-submit-btn').prop('disabled', true);
      } else {
        $('#reset-token').val(token);
        $('#reset-email').val(email);
      }

      // Password toggle
      $('#toggle-new-password').on('click', function () {
        const $input = $('#reset-new-password');
        const $icon = $('#toggle-new-password-icon');
        if ($input.attr('type') === 'password') {
          $input.attr('type', 'text');
          $icon.removeClass('bi-eye').addClass('bi-eye-slash');
        } else {
          $input.attr('type', 'password');
          $icon.removeClass('bi-eye-slash').addClass('bi-eye');
        }
      });

      // Submit new password
      $('#reset-password-form').on('submit', function (e) {
        e.preventDefault();
        const t = $('#reset-token').val();
        const em = $('#reset-email').val();
        const p1 = $('#reset-new-password').val();
        const p2 = $('#reset-confirm-password').val();
        const cred = $('#reset-credential').val().trim();
        const $btn = $('#reset-submit-btn');
        const $alert = $('#reset-alert');

        if (p1 !== p2) {
          $alert.removeClass('d-none').addClass('alert-danger').html('<i class="bi bi-x-circle me-1"></i>Passwords do not match.');
          return;
        }

        if (p1.length < 8) {
          $alert.removeClass('d-none').addClass('alert-danger').html('<i class="bi bi-x-circle me-1"></i>Password must be at least 8 characters.');
          return;
        }

        $alert.addClass('d-none').removeClass('alert-danger alert-success');
        $btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm me-2"></span>Updating Credentials...');

        LG.api.request({
          url: '/auth/reset-password',
          method: 'POST',
          data: {
            token: t,
            email: em,
            new_password: p1,
            credential_id: cred || null
          }
        }).done(function (res) {
          $alert.removeClass('d-none').addClass('alert-success').html(`
            <i class="bi bi-check-circle-fill me-1"></i>${LG.utils.escapeHtml(res.message)}
            <div class="mt-2 font-semibold">Redirecting to sign in portal...</div>
          `);
          LG.toast('Password updated successfully! Redirecting...', 'success');
          setTimeout(function () {
            window.location.href = 'login.html';
          }, 2000);
        }).fail(function (xhr) {
          $btn.prop('disabled', false).html('<span>Update Password</span> <i class="bi bi-arrow-right"></i>');
          let err = 'Unable to reset password.';
          if (xhr.responseJSON && xhr.responseJSON.detail) {
            err = xhr.responseJSON.detail;
          }
          $alert.removeClass('d-none').addClass('alert-danger').html(`
            <i class="bi bi-shield-x me-1"></i>${LG.utils.escapeHtml(err)}
          `);
          LG.toast(err, 'danger');
        });
      });
    });
