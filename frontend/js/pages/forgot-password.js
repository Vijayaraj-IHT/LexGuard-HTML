    $(document).ready(function () {
      $('#forgot-password-form').on('submit', function (e) {
        e.preventDefault();
        const email = $('#recovery-email').val().trim();
        const credId = $('#recovery-credential').val().trim();
        const $btn = $('#recovery-submit-btn');
        const $alert = $('#recovery-alert');
        const $devBox = $('#dev-link-container');

        $alert.addClass('d-none').removeClass('alert-danger alert-success alert-warning alert-info');
        $devBox.addClass('d-none');
        $btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm me-2"></span>Verifying...');

        LG.api.request({
          url: '/auth/forgot-password',
          method: 'POST',
          data: {
            email: email,
            credential_id: credId || null
          }
        }).done(function (res) {
          $btn.prop('disabled', false).html('<span>Initiate Recovery</span> <i class="bi bi-shield-check"></i>');

          if (res.reset_mode === 'staff_ticket_filed') {
            $alert.removeClass('d-none').addClass('alert-warning').html(`
              <div class="d-flex align-items-start gap-2">
                <i class="bi bi-exclamation-triangle-fill fs-5 mt-1 text-warning"></i>
                <div>
                  <strong>Staff Security Protocol:</strong><br>
                  ${LG.utils.escapeHtml(res.message)}
                </div>
              </div>
            `);
            LG.toast('Staff reset ticket filed for supervisor review.', 'warning');
          } else if (res.reset_mode === 'direct_token') {
            $alert.removeClass('d-none').addClass('alert-success').html(`
              <div class="d-flex align-items-start gap-2">
                <i class="bi bi-check-circle-fill fs-5 mt-1 text-success"></i>
                <div>
                  <strong>Verification Success:</strong><br>
                  ${LG.utils.escapeHtml(res.message)}
                </div>
              </div>
            `);
            LG.toast('Password reset link issued.', 'success');

            if (res.dev_reset_url) {
              $devBox.removeClass('d-none');
              $('#dev-reset-link').attr('href', res.dev_reset_url);
            }
          } else {
            $alert.removeClass('d-none').addClass('alert-info').text(res.message);
          }
        }).fail(function (xhr) {
          $btn.prop('disabled', false).html('<span>Initiate Recovery</span> <i class="bi bi-shield-check"></i>');
          let err = 'Unable to process recovery request.';
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
